"""Piyasa verisi katmanı: canlı FRED verisi, temsili veri setleri ve CSV G/Ç.

Üç veri kaynağı desteklenir:

1. **Canlı FRED** — ABD Hazine sabit vadeli getiri serileri (DGS3MO ...
   DGS30) FRED'in halka açık CSV uç noktasından çekilir
   (``https://fred.stlouisfed.org/graph/fredgraph.csv``). İnternet yoksa
   veya istek başarısız olursa SESSİZCE gömülü temsili veriye düşülür.

2. **Gömülü temsili setler** — açıkça "temsili/örnek veri" olarak
   etiketlenmiş, tarih bilgili iki set:
   * Türkiye DİBS örnek kotasyonları (yüksek TL faiz ortamına uygun
     seviyeler; kupon, fiyat, getiri).
   * ABD Hazine örnek eğrisi.

3. **Kullanıcı CSV'leri** — ``data/`` klasörüne yazılan örnek CSV'lerle
   aynı şemada kendi verinizi koyup yükleyebilirsiniz
   (:func:`tahvilleri_csvden_yukle`, :func:`egriyi_csvden_yukle`).

Not: FRED sabit vadeli getirileri (CMT) par getiriye yakındır; bu modül
eğriyi görselleştirme/analiz amacıyla doğrudan spot yaklaşımı olarak da
sunar, istenirse kotasyonlardan bootstrap için enstrüman listesi üretir.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from bond_lab.bond import Tahvil
from bond_lab.pricing import temiz_fiyat, ytm_bul
from bond_lab.yield_curve import GetiriEgrisi

#: FRED serisi → vade (yıl) eşlemesi.
FRED_SERILERI: dict[str, float] = {
    "DGS3MO": 0.25,
    "DGS6MO": 0.5,
    "DGS1": 1.0,
    "DGS2": 2.0,
    "DGS5": 5.0,
    "DGS10": 10.0,
    "DGS30": 30.0,
}

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

VARSAYILAN_VERI_KLASORU = Path("data")


# ----------------------------------------------------------------------
# Veri türleri
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class PiyasaEgrisi:
    """Vade–getiri noktalarından oluşan basit piyasa eğrisi kaydı.

    Attributes:
        vadeler: Vade noktaları (yıl), artan sıralı.
        oranlar: Karşılık gelen yıllık getiriler (ondalık).
        kaynak: Verinin kaynağı (ör. ``"FRED (canlı)"`` veya
            ``"Temsili örnek veri"``).
        tarih: Verinin ait olduğu tarih (ISO metni).
    """

    vadeler: tuple[float, ...]
    oranlar: tuple[float, ...]
    kaynak: str
    tarih: str

    def spot_egri(self, interpolasyon: str = "dogrusal") -> GetiriEgrisi:
        """Noktaları doğrudan spot eğri olarak sarar (CMT ≈ spot yaklaşımı)."""
        return GetiriEgrisi(list(self.vadeler), list(self.oranlar), interpolasyon)


@dataclass(frozen=True)
class TahvilKotasyonu:
    """Tek bir tahvil piyasa kotasyonu (isim, sözleşme şartları, fiyat, getiri)."""

    isim: str
    vade_yil: float
    kupon_orani: float
    frekans: int
    ytm: float
    temiz_fiyat: float

    def tahvil(self) -> Tahvil:
        """Kotasyona karşılık gelen :class:`Tahvil` nesnesi."""
        return Tahvil(
            nominal=100.0,
            kupon_orani=self.kupon_orani,
            vade_yil=self.vade_yil,
            frekans=self.frekans,
            isim=self.isim,
        )


# ----------------------------------------------------------------------
# Gömülü temsili veri setleri
# ----------------------------------------------------------------------
#: Temsili verilerin ait olduğu (kurgusal) referans tarihi.
ORNEK_VERI_TARIHI = "2026-06-30"

ORNEK_VERI_UYARISI = (
    "TEMSİLİ/ÖRNEK VERİ — gerçek piyasa kotasyonu değildir; "
    f"{ORNEK_VERI_TARIHI} tarihli seviyelere göre kurgulanmıştır."
)

# Türkiye DİBS örnek seti: (isim, vade_yil, kupon, frekans, ytm).
# Yüksek TL faiz ortamı: kısa uç ~%38-40, uzun uç ~%23 (ters eğri).
_DIBS_HAM: tuple[tuple[str, float, float, int, float], ...] = (
    ("TRT 6A iskontolu", 0.5, 0.00, 1, 0.395),
    ("TRT 1Y iskontolu", 1.0, 0.00, 1, 0.370),
    ("TRT 2Y %32 kuponlu", 2.0, 0.32, 2, 0.335),
    ("TRT 3Y %30 kuponlu", 3.0, 0.30, 2, 0.305),
    ("TRT 5Y %26 kuponlu", 5.0, 0.26, 2, 0.272),
    ("TRT 7Y %24 kuponlu", 7.0, 0.24, 2, 0.250),
    ("TRT 10Y %22 kuponlu", 10.0, 0.22, 2, 0.234),
)

# ABD Hazine örnek eğrisi (vade yıl → getiri), hafif dik normal eğri.
_UST_HAM: tuple[tuple[float, float], ...] = (
    (0.25, 0.0430),
    (0.5, 0.0424),
    (1.0, 0.0412),
    (2.0, 0.0393),
    (5.0, 0.0388),
    (10.0, 0.0407),
    (30.0, 0.0446),
)


def dibs_ornek_seti() -> list[TahvilKotasyonu]:
    """Türkiye DİBS temsili kotasyon seti (fiyatlar getirilerle tutarlı).

    Temiz fiyatlar, gömülü getirilerden çekirdek fiyatlama fonksiyonuyla
    hesaplanır; böylece set arbitrajsız ve gidiş-dönüş testine uygundur.
    """
    kotasyonlar: list[TahvilKotasyonu] = []
    for isim, vade, kupon, frekans, ytm in _DIBS_HAM:
        t = Tahvil(nominal=100.0, kupon_orani=kupon, vade_yil=vade, frekans=frekans, isim=isim)
        kotasyonlar.append(
            TahvilKotasyonu(
                isim=isim,
                vade_yil=vade,
                kupon_orani=kupon,
                frekans=frekans,
                ytm=ytm,
                temiz_fiyat=round(temiz_fiyat(t, ytm), 4),
            )
        )
    return kotasyonlar


def ust_ornek_egrisi() -> PiyasaEgrisi:
    """ABD Hazine temsili getiri eğrisi (gömülü)."""
    vadeler = tuple(v for v, _ in _UST_HAM)
    oranlar = tuple(o for _, o in _UST_HAM)
    return PiyasaEgrisi(
        vadeler=vadeler,
        oranlar=oranlar,
        kaynak=f"Temsili örnek veri ({ORNEK_VERI_UYARISI})",
        tarih=ORNEK_VERI_TARIHI,
    )


def dibs_ornek_egrisi() -> PiyasaEgrisi:
    """DİBS örnek setindeki getirilerden vade–getiri eğrisi."""
    kotasyonlar = dibs_ornek_seti()
    return PiyasaEgrisi(
        vadeler=tuple(k.vade_yil for k in kotasyonlar),
        oranlar=tuple(k.ytm for k in kotasyonlar),
        kaynak=f"Temsili örnek veri ({ORNEK_VERI_UYARISI})",
        tarih=ORNEK_VERI_TARIHI,
    )


# ----------------------------------------------------------------------
# Canlı FRED çekimi
# ----------------------------------------------------------------------
def _fred_csv_ayristir(metin: str) -> dict[str, tuple[str, float]]:
    """fredgraph.csv çıktısını ayrıştırır.

    Her seri için (tarih, değer) çifti döndürür; '.' işaretli eksik
    gözlemler atlanır ve serinin SON geçerli gözlemi alınır. Değerler
    yüzde cinsindedir, ondalığa çevrilir.
    """
    okuyucu = csv.reader(io.StringIO(metin))
    satirlar = [s for s in okuyucu if s]
    if len(satirlar) < 2:
        return {}
    baslik = [h.strip() for h in satirlar[0]]
    # İlk sütun tarih (DATE veya observation_date), kalanlar seriler.
    sonuc: dict[str, tuple[str, float]] = {}
    for satir in satirlar[1:]:
        if len(satir) != len(baslik):
            continue
        tarih_str = satir[0].strip()
        for i in range(1, len(baslik)):
            ham = satir[i].strip()
            if ham in (".", ""):
                continue
            try:
                deger = float(ham) / 100.0
            except ValueError:
                continue
            sonuc[baslik[i]] = (tarih_str, deger)
    return sonuc


def fred_hazine_egrisi(
    zaman_asimi: float = 20.0,
    seriler: dict[str, float] | None = None,
) -> PiyasaEgrisi | None:
    """FRED'den güncel ABD Hazine eğrisini çekmeyi dener.

    Tek bir HTTP isteğiyle tüm seriler (virgülle birleştirilmiş id
    parametresi) son ~45 günlük pencerede istenir; her serinin son
    geçerli gözlemi alınır.

    Args:
        zaman_asimi: HTTP zaman aşımı (saniye).
        seriler: Seri→vade eşlemesi; None ise :data:`FRED_SERILERI`.

    Returns:
        Başarılıysa :class:`PiyasaEgrisi`, aksi halde ``None``
        (istisna fırlatmaz; çağıran gömülü veriye düşebilir).
    """
    if seriler is None:
        seriler = FRED_SERILERI
    try:
        import requests  # yerel import: modül internetsiz ortamda da yüklenebilsin

        baslangic = (date.today() - timedelta(days=45)).isoformat()
        yanit = requests.get(
            FRED_CSV_URL,
            params={"id": ",".join(seriler.keys()), "cosd": baslangic},
            timeout=zaman_asimi,
        )
        yanit.raise_for_status()
        gozlemler = _fred_csv_ayristir(yanit.text)
    except Exception:
        return None

    noktalar: list[tuple[float, float, str]] = []
    for seri, vade in seriler.items():
        if seri in gozlemler:
            tarih_str, oran = gozlemler[seri]
            noktalar.append((vade, oran, tarih_str))
    if len(noktalar) < 4:  # eğri çizecek kadar nokta yoksa başarısız say
        return None
    noktalar.sort(key=lambda x: x[0])
    son_tarih = max(n[2] for n in noktalar)
    return PiyasaEgrisi(
        vadeler=tuple(n[0] for n in noktalar),
        oranlar=tuple(n[1] for n in noktalar),
        kaynak="FRED (canlı)",
        tarih=son_tarih,
    )


def ust_egrisi_getir(canli_dene: bool = True, zaman_asimi: float = 20.0) -> PiyasaEgrisi:
    """ABD Hazine eğrisini getirir: önce FRED, olmazsa gömülü temsili veri.

    Args:
        canli_dene: False ise doğrudan gömülü veri kullanılır.
        zaman_asimi: FRED isteği zaman aşımı (saniye).
    """
    if canli_dene:
        canli = fred_hazine_egrisi(zaman_asimi=zaman_asimi)
        if canli is not None:
            return canli
    return ust_ornek_egrisi()


# ----------------------------------------------------------------------
# CSV yazma / yükleme
# ----------------------------------------------------------------------
TAHVIL_CSV_ALANLARI = ["isim", "vade_yil", "kupon_orani", "frekans", "ytm", "temiz_fiyat"]
EGRI_CSV_ALANLARI = ["vade_yil", "oran"]


def ornek_csvleri_yaz(klasor: Path | None = None) -> list[Path]:
    """Örnek veri CSV'lerini ``data/`` klasörüne yazar.

    Üretilenler:
        * ``dibs_ornek.csv``  — DİBS kotasyon seti (tahvil şeması).
        * ``ust_egri_ornek.csv`` — ABD Hazine örnek eğrisi (eğri şeması).

    Returns:
        Yazılan dosya yolları.
    """
    hedef = Path(klasor) if klasor is not None else VARSAYILAN_VERI_KLASORU
    hedef.mkdir(parents=True, exist_ok=True)
    yollar: list[Path] = []

    dibs_yolu = hedef / "dibs_ornek.csv"
    with open(dibs_yolu, "w", newline="", encoding="utf-8-sig") as f:
        f.write(f"# {ORNEK_VERI_UYARISI}\n")
        yazici = csv.DictWriter(f, fieldnames=TAHVIL_CSV_ALANLARI)
        yazici.writeheader()
        for k in dibs_ornek_seti():
            yazici.writerow(
                {
                    "isim": k.isim,
                    "vade_yil": k.vade_yil,
                    "kupon_orani": k.kupon_orani,
                    "frekans": k.frekans,
                    "ytm": k.ytm,
                    "temiz_fiyat": k.temiz_fiyat,
                }
            )
    yollar.append(dibs_yolu)

    egri = ust_ornek_egrisi()
    egri_yolu = hedef / "ust_egri_ornek.csv"
    with open(egri_yolu, "w", newline="", encoding="utf-8-sig") as f:
        f.write(f"# {ORNEK_VERI_UYARISI}\n")
        yazici = csv.DictWriter(f, fieldnames=EGRI_CSV_ALANLARI)
        yazici.writeheader()
        for v, o in zip(egri.vadeler, egri.oranlar, strict=True):
            yazici.writerow({"vade_yil": v, "oran": o})
    yollar.append(egri_yolu)
    return yollar


def _csv_satirlari(yol: Path) -> list[dict[str, str]]:
    """CSV satırlarını okur; '#' ile başlayan yorum satırlarını atlar."""
    with open(yol, encoding="utf-8-sig") as f:
        icerik = [satir for satir in f if not satir.lstrip().startswith("#")]
    okuyucu = csv.DictReader(io.StringIO("".join(icerik)))
    return [dict(satir) for satir in okuyucu]


def tahvilleri_csvden_yukle(yol: Path) -> list[TahvilKotasyonu]:
    """Tahvil kotasyonlarını CSV'den yükler.

    Beklenen sütunlar: ``isim, vade_yil, kupon_orani, frekans, ytm,
    temiz_fiyat`` (örnek: ``data/dibs_ornek.csv``). ``ytm`` veya
    ``temiz_fiyat`` alanlarından biri boşsa diğerinden türetilir.

    Raises:
        ValueError: Zorunlu sütunlar eksikse veya satır ayrıştırılamazsa.
        FileNotFoundError: Dosya yoksa.
    """
    yol = Path(yol)
    satirlar = _csv_satirlari(yol)
    if not satirlar:
        raise ValueError(f"{yol} dosyasında veri satırı bulunamadı.")
    kotasyonlar: list[TahvilKotasyonu] = []
    for i, satir in enumerate(satirlar, start=1):
        try:
            isim = (satir.get("isim") or f"Tahvil {i}").strip()
            vade = float(satir["vade_yil"])
            kupon = float(satir["kupon_orani"])
            frekans = int(float(satir.get("frekans") or 1))
            t = Tahvil(nominal=100.0, kupon_orani=kupon, vade_yil=vade, frekans=frekans, isim=isim)

            ytm_ham = (satir.get("ytm") or "").strip()
            fiyat_ham = (satir.get("temiz_fiyat") or "").strip()
            if ytm_ham:
                ytm = float(ytm_ham)
                fiyat = float(fiyat_ham) if fiyat_ham else round(temiz_fiyat(t, ytm), 6)
            elif fiyat_ham:
                fiyat = float(fiyat_ham)
                ytm = ytm_bul(t, fiyat, temiz=True)
            else:
                raise KeyError("ytm veya temiz_fiyat")
            kotasyonlar.append(
                TahvilKotasyonu(
                    isim=isim,
                    vade_yil=vade,
                    kupon_orani=kupon,
                    frekans=frekans,
                    ytm=ytm,
                    temiz_fiyat=fiyat,
                )
            )
        except (KeyError, TypeError, ValueError) as hata:
            raise ValueError(f"{yol} dosyasının {i}. satırı okunamadı: {hata}") from hata
    return kotasyonlar


def egriyi_csvden_yukle(yol: Path) -> PiyasaEgrisi:
    """Vade–getiri eğrisini CSV'den yükler.

    Beklenen sütunlar: ``vade_yil, oran`` (örnek: ``data/ust_egri_ornek.csv``).

    Raises:
        ValueError: Sütunlar eksik veya sayıya çevrilemiyorsa.
        FileNotFoundError: Dosya yoksa.
    """
    yol = Path(yol)
    satirlar = _csv_satirlari(yol)
    if not satirlar:
        raise ValueError(f"{yol} dosyasında veri satırı bulunamadı.")
    noktalar: list[tuple[float, float]] = []
    for i, satir in enumerate(satirlar, start=1):
        try:
            noktalar.append((float(satir["vade_yil"]), float(satir["oran"])))
        except (KeyError, TypeError, ValueError) as hata:
            raise ValueError(f"{yol} dosyasının {i}. satırı okunamadı: {hata}") from hata
    noktalar.sort(key=lambda x: x[0])
    return PiyasaEgrisi(
        vadeler=tuple(v for v, _ in noktalar),
        oranlar=tuple(o for _, o in noktalar),
        kaynak=f"CSV: {yol.name}",
        tarih="",
    )


def kotasyonlardan_enstrumanlar(
    kotasyonlar: Sequence[TahvilKotasyonu],
) -> list[tuple[Tahvil, float]]:
    """Kotasyon listesini bootstrap için (tahvil, temiz fiyat) çiftlerine çevirir."""
    return [(k.tahvil(), k.temiz_fiyat) for k in kotasyonlar]
