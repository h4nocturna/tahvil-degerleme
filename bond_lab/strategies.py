"""Tahvil yatırım stratejileri motoru.

İçerik:
    * Portföy kurucuları: :func:`merdiven_portfoy` (ladder),
      :func:`barbell_portfoy` (halter), :func:`bullet_portfoy` (mermi).
    * :func:`senaryo_analizi` — faiz senaryoları altında portföy değer
      değişimi; :func:`standart_senaryolar` paralel kaymalar (±50/±100/
      ±200bp) ile dikleşme/yataylaşma senaryolarını üretir.
    * :func:`immunizasyon_portfoy` — hedef yatırım ufkuna Macaulay
      durasyonu eşleyen iki tahvilli klasik immünizasyon.
    * :func:`strateji_oner` — kullanıcının faiz beklentisi, ufku ve risk
      toleransına göre Türkçe gerekçeli strateji önerisi.

Kurucularda tahviller, verilen getiri eğrisine göre KUPONU = GETİRİSİ
olan par tahviller olarak yaratılır (fiyat = nominal); böylece para
ağırlıkları doğrudan hedeflenen dağılımı verir. İstenirse sabit bir
kupon oranı da geçilebilir.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from bond_lab.bond import Tahvil
from bond_lab.portfolio import Portfoy, Pozisyon
from bond_lab.pricing import kirli_fiyat
from bond_lab.risk import macaulay_durasyon
from bond_lab.yield_curve import GetiriEgrisi

#: Getiri kaynağı: eğri ya da vade→getiri fonksiyonu.
GetiriKaynagi = GetiriEgrisi | Callable[[float], float]

#: Faiz senaryosu: vade (yıl) → getiri kayması (ondalık).
Senaryo = Callable[[float], float]

GECERLI_BEKLENTILER = ("yukselecek", "dusecek", "sabit")
GECERLI_TOLERANSLAR = ("dusuk", "orta", "yuksek")


def _getiri_fonksiyonu(kaynak: GetiriKaynagi) -> Callable[[float], float]:
    """Getiri kaynağını vade→getiri fonksiyonuna çevirir."""
    if isinstance(kaynak, GetiriEgrisi):
        return kaynak.spot_oran
    if callable(kaynak):
        return kaynak
    raise TypeError("Getiri kaynağı GetiriEgrisi veya çağrılabilir olmalıdır.")


def _pozisyon_kur(
    tutar: float,
    vade: float,
    getiri: Callable[[float], float],
    frekans: int,
    kupon_orani: float | None,
    isim: str,
) -> Pozisyon:
    """Verilen tutarı tek vadeye yatıran pozisyon üretir.

    kupon_orani None ise tahvil par kurulur (kupon = o vadenin getirisi).
    """
    if tutar <= 0:
        raise ValueError("Yatırım tutarı pozitif olmalıdır.")
    y = getiri(vade)
    kupon = y if kupon_orani is None else kupon_orani
    tahvil = Tahvil(nominal=100.0, kupon_orani=kupon, vade_yil=vade, frekans=frekans, isim=isim)
    birim = kirli_fiyat(tahvil, y)
    return Pozisyon(tahvil=tahvil, adet=tutar / birim, ytm=y)


# ----------------------------------------------------------------------
# Strateji kurucuları
# ----------------------------------------------------------------------
def merdiven_portfoy(
    toplam_tutar: float,
    vadeler: Sequence[float],
    getiri: GetiriKaynagi,
    frekans: int = 1,
    kupon_orani: float | None = None,
) -> Portfoy:
    """Merdiven (ladder) stratejisi: tutarı vadelere EŞİT böler.

    Her yıl/vade basamağına eşit para yatırılır; vadesi gelen anapara
    yeniden en uzun basamağa yatırılarak çevrilir (bu kurucular tek
    seferlik anlık portföyü kurar).

    Args:
        toplam_tutar: Toplam yatırım tutarı.
        vadeler: Basamak vadeleri (yıl), en az 2 nokta.
        getiri: Getiri eğrisi veya vade→getiri fonksiyonu.
        frekans: Kurulan tahvillerin kupon frekansı.
        kupon_orani: None ise par tahvil (kupon=getiri).

    Raises:
        ValueError: Vade sayısı 2'den azsa veya tutar pozitif değilse.
    """
    if len(vadeler) < 2:
        raise ValueError("Merdiven için en az 2 vade gereklidir.")
    g = _getiri_fonksiyonu(getiri)
    dilim = toplam_tutar / len(vadeler)
    portfoy = Portfoy(isim="Merdiven (Ladder)")
    for v in vadeler:
        portfoy.ekle(_pozisyon_kur(dilim, v, g, frekans, kupon_orani, f"Merdiven {v:g}Y"))
    return portfoy


def bullet_portfoy(
    toplam_tutar: float,
    hedef_vade: float,
    getiri: GetiriKaynagi,
    frekans: int = 1,
    kupon_orani: float | None = None,
) -> Portfoy:
    """Bullet (mermi) stratejisi: tüm tutar TEK hedef vadeye yatırılır.

    Nakit ihtiyacının zamanı kesin olarak bilindiğinde (örn. 5 yıl sonra
    okul/ev ödemesi) hedef vadeye odaklanmak için kullanılır.
    """
    g = _getiri_fonksiyonu(getiri)
    portfoy = Portfoy(isim="Bullet (Mermi)")
    portfoy.ekle(
        _pozisyon_kur(toplam_tutar, hedef_vade, g, frekans, kupon_orani, f"Bullet {hedef_vade:g}Y")
    )
    return portfoy


def barbell_portfoy(
    toplam_tutar: float,
    kisa_vade: float,
    uzun_vade: float,
    getiri: GetiriKaynagi,
    kisa_agirlik: float = 0.5,
    frekans: int = 1,
    kupon_orani: float | None = None,
) -> Portfoy:
    """Barbell (halter) stratejisi: yalnız KISA ve UZUN uçlara yatırım.

    Kısa uç likidite/yeniden yatırım esnekliği, uzun uç getiri ve
    konveksite sağlar; orta vadeler boş bırakılır.

    Args:
        kisa_agirlik: Kısa uca ayrılan para oranı (0-1 arasında, uçlar hariç).

    Raises:
        ValueError: kisa_vade >= uzun_vade veya ağırlık (0,1) dışında ise.
    """
    if kisa_vade >= uzun_vade:
        raise ValueError("Kısa vade uzun vadeden küçük olmalıdır.")
    if not 0.0 < kisa_agirlik < 1.0:
        raise ValueError("kisa_agirlik 0 ile 1 arasında olmalıdır.")
    g = _getiri_fonksiyonu(getiri)
    portfoy = Portfoy(isim="Barbell (Halter)")
    portfoy.ekle(
        _pozisyon_kur(
            toplam_tutar * kisa_agirlik,
            kisa_vade,
            g,
            frekans,
            kupon_orani,
            f"Barbell kısa {kisa_vade:g}Y",
        )
    )
    portfoy.ekle(
        _pozisyon_kur(
            toplam_tutar * (1.0 - kisa_agirlik),
            uzun_vade,
            g,
            frekans,
            kupon_orani,
            f"Barbell uzun {uzun_vade:g}Y",
        )
    )
    return portfoy


# ----------------------------------------------------------------------
# İmmünizasyon
# ----------------------------------------------------------------------
def immunizasyon_portfoy(
    toplam_tutar: float,
    hedef_ufuk: float,
    kisa_vade: float,
    uzun_vade: float,
    getiri: GetiriKaynagi,
    frekans: int = 1,
) -> Portfoy:
    """Hedef ufka Macaulay durasyonu eşleyen iki tahvilli immünizasyon.

    Kısa ve uzun vadeli iki par tahvilin durasyonları ``D_k < H < D_u``
    koşulunu sağlıyorsa, ``w·D_k + (1−w)·D_u = H`` denkleminden kısa
    tahvil ağırlığı çözülür. Böylece portföyün durasyonu yatırım ufkuna
    eşitlenir; küçük paralel faiz oynamalarında fiyat riski ile yeniden
    yatırım riski birbirini dengeler.

    Args:
        toplam_tutar: Toplam yatırım.
        hedef_ufuk: Yatırım ufku (yıl) = hedeflenen Macaulay durasyonu.
        kisa_vade / uzun_vade: Kullanılacak iki tahvilin vadeleri.
        getiri: Getiri eğrisi veya fonksiyonu.
        frekans: Kupon frekansı.

    Returns:
        Durasyonu hedefe eşitlenmiş :class:`Portfoy`.

    Raises:
        ValueError: Hedef, iki tahvilin durasyonları arasında değilse.
    """
    g = _getiri_fonksiyonu(getiri)
    kisa = _pozisyon_kur(1.0, kisa_vade, g, frekans, None, f"İmm. kısa {kisa_vade:g}Y")
    uzun = _pozisyon_kur(1.0, uzun_vade, g, frekans, None, f"İmm. uzun {uzun_vade:g}Y")
    d_kisa = macaulay_durasyon(kisa.tahvil, kisa.ytm)
    d_uzun = macaulay_durasyon(uzun.tahvil, uzun.ytm)
    if not d_kisa < hedef_ufuk < d_uzun:
        raise ValueError(
            f"Hedef ufuk ({hedef_ufuk:g} yıl) iki tahvilin durasyonları arasında "
            f"olmalıdır: D_kısa={d_kisa:.3f}, D_uzun={d_uzun:.3f}."
        )
    w_kisa = (d_uzun - hedef_ufuk) / (d_uzun - d_kisa)
    portfoy = Portfoy(isim=f"İmmünizasyon (ufuk {hedef_ufuk:g}Y)")
    portfoy.ekle(
        _pozisyon_kur(
            toplam_tutar * w_kisa,
            kisa_vade,
            g,
            frekans,
            None,
            f"İmm. kısa {kisa_vade:g}Y",
        )
    )
    portfoy.ekle(
        _pozisyon_kur(
            toplam_tutar * (1.0 - w_kisa),
            uzun_vade,
            g,
            frekans,
            None,
            f"İmm. uzun {uzun_vade:g}Y",
        )
    )
    return portfoy


# ----------------------------------------------------------------------
# Senaryo analizi
# ----------------------------------------------------------------------
def standart_senaryolar(egim_pivot: float = 10.0, egim_bp: float = 50.0) -> dict[str, Senaryo]:
    """Standart faiz senaryoları sözlüğü.

    Paralel kaymalar (±50, ±100, ±200bp) ile dikleşme/yataylaşma içerir.
    Dikleşme: kısa uç −egim_bp, ``egim_pivot`` yıl ve ötesi +egim_bp
    (arada doğrusal geçiş). Yataylaşma bunun aynadaki görüntüsüdür.

    Args:
        egim_pivot: Eğim senaryolarında uzun ucun başladığı vade (yıl).
        egim_bp: Eğim senaryolarının uçlardaki büyüklüğü (baz puan).
    """

    def paralel(bp: float) -> Senaryo:
        return lambda vade: bp / 10000.0

    def diklesme(vade: float) -> float:
        oran = min(max(vade / egim_pivot, 0.0), 1.0)
        return (-egim_bp + 2.0 * egim_bp * oran) / 10000.0

    def yataylasma(vade: float) -> float:
        return -diklesme(vade)

    senaryolar: dict[str, Senaryo] = {}
    for bp in (-200, -100, -50, 50, 100, 200):
        isaret = "+" if bp > 0 else ""
        senaryolar[f"Paralel {isaret}{bp}bp"] = paralel(bp)
    senaryolar["Dikleşme (kısa−/uzun+)"] = diklesme
    senaryolar["Yataylaşma (kısa+/uzun−)"] = yataylasma
    return senaryolar


def senaryo_analizi(
    portfoy: Portfoy, senaryolar: dict[str, Senaryo] | None = None
) -> dict[str, dict[str, float]]:
    """Portföyü senaryolar altında yeniden fiyatlar.

    Args:
        portfoy: Analiz edilecek portföy.
        senaryolar: İsim→kayma fonksiyonu sözlüğü; None ise
            :func:`standart_senaryolar` kullanılır.

    Returns:
        Her senaryo için ``{"baslangic_deger", "yeni_deger",
        "degisim", "degisim_yuzde"}`` içeren sözlük.
    """
    if not portfoy.pozisyonlar:
        raise ValueError("Senaryo analizi için portföyde en az bir pozisyon olmalıdır.")
    if senaryolar is None:
        senaryolar = standart_senaryolar()
    baslangic = portfoy.toplam_deger
    sonuc: dict[str, dict[str, float]] = {}
    for isim, kayma in senaryolar.items():
        yeni = portfoy.senaryo_degeri(kayma)
        sonuc[isim] = {
            "baslangic_deger": baslangic,
            "yeni_deger": yeni,
            "degisim": yeni - baslangic,
            "degisim_yuzde": (yeni / baslangic - 1.0) * 100.0,
        }
    return sonuc


# ----------------------------------------------------------------------
# Strateji önerisi
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class StratejiOnerisi:
    """Strateji öneri motorunun çıktısı.

    Attributes:
        strateji: Önerilen stratejinin adı (merdiven/barbell/bullet/immünizasyon).
        hedef_durasyon: Önerilen yaklaşık portföy durasyonu (yıl).
        gerekce: Türkçe, insan okunur gerekçe metni.
    """

    strateji: str
    hedef_durasyon: float
    gerekce: str


def strateji_oner(faiz_beklentisi: str, ufuk_yil: float, risk_toleransi: str) -> StratejiOnerisi:
    """Kullanıcı profiline göre tahvil stratejisi önerir.

    Karar mantığı (özet):
        * Faiz YÜKSELECEK → durasyonu kısalt: fiyat kaybını sınırla,
          vadesi gelen parayı yükselen faizden yeniden yatır. Düşük
          riskte kısa merdiven, yüksek riskte kısa ağırlıklı barbell.
        * Faiz DÜŞECEK → durasyonu uzat: fiyat kazancını büyüt. Düşük
          riskte ufka eşlenmiş immünizasyon/bullet, yüksek riskte uzun
          bullet (durasyon > ufuk).
        * Faiz SABİT → taşıma (carry) ve çevirme getirisine odaklan:
          düşük riskte immünizasyon, orta riskte merdiven, yüksek riskte
          eğrinin dik bölgesinden yararlanan barbell.

    Args:
        faiz_beklentisi: ``"yukselecek"``, ``"dusecek"`` veya ``"sabit"``.
        ufuk_yil: Yatırım ufku (yıl), pozitif.
        risk_toleransi: ``"dusuk"``, ``"orta"`` veya ``"yuksek"``.

    Returns:
        :class:`StratejiOnerisi` (Türkçe gerekçeli).

    Raises:
        ValueError: Girdiler geçerli kümelerde değilse.
    """
    beklenti = faiz_beklentisi.strip().lower()
    tolerans = risk_toleransi.strip().lower()
    if beklenti not in GECERLI_BEKLENTILER:
        raise ValueError(f"faiz_beklentisi {GECERLI_BEKLENTILER} içinden olmalıdır.")
    if tolerans not in GECERLI_TOLERANSLAR:
        raise ValueError(f"risk_toleransi {GECERLI_TOLERANSLAR} içinden olmalıdır.")
    if ufuk_yil <= 0:
        raise ValueError("Yatırım ufku pozitif olmalıdır.")

    if beklenti == "yukselecek":
        hedef_durasyon = min(ufuk_yil, 2.0) if tolerans == "dusuk" else min(ufuk_yil, 3.0)
        if tolerans == "yuksek":
            strateji = "barbell"
            ek = (
                "Kısa ağırlıklı bir barbell (halter) kurun: paranın büyük kısmı kısa "
                "uçta faiz artışından korunurken, küçük bir uzun uç pozisyonu beklenti "
                "yanılırsa getiri sağlar."
            )
        else:
            strateji = "merdiven"
            ek = (
                "Kısa vadeli bir merdiven (ladder) kurun: her yıl vadesi gelen anapara, "
                "yükselen faiz ortamında daha yüksek getiriyle yeniden yatırılır."
            )
        gerekce = (
            f"Faizlerin YÜKSELMESİNİ bekliyorsunuz. Faiz artışı tahvil fiyatlarını "
            f"düşürdüğü için portföy durasyonunu kısa tutmak (yaklaşık "
            f"{hedef_durasyon:.1f} yıl) fiyat kaybını sınırlar. {ek} "
            f"Uzun vadeli sabit kuponlu tahvillerden ve durasyonu ufkunuzdan uzun "
            f"pozisyonlardan kaçının."
        )
    elif beklenti == "dusecek":
        if tolerans == "dusuk":
            strateji = "immünizasyon"
            hedef_durasyon = ufuk_yil
            ek = (
                "Düşük risk toleransıyla en sağlamı, durasyonu yatırım ufkunuza "
                "eşitleyen immünizasyondur: faiz düşüşünün fiyat kazancı, kuponların "
                "daha düşük faizle yeniden yatırım kaybını dengeler."
            )
        elif tolerans == "orta":
            strateji = "barbell"
            hedef_durasyon = ufuk_yil * 1.15
            ek = (
                "Barbell (halter) ile uzun uçtan fiyat kazancı hedeflerken kısa uç "
                "likidite tamponu sağlar; barbell aynı durasyonlu bullet'a göre daha "
                "yüksek konveksite taşıdığından büyük faiz düşüşlerinde avantajlıdır."
            )
        else:
            strateji = "bullet"
            hedef_durasyon = ufuk_yil * 1.4
            ek = (
                "Yüksek risk toleransıyla, durasyonu ufkunuzun üzerinde uzun vadeli "
                "bir bullet (mermi) pozisyonu faiz düşüşünden en yüksek fiyat "
                "kazancını sağlar; karşılığında faiz yükselirse kayıp da büyüktür."
            )
        gerekce = (
            f"Faizlerin DÜŞMESİNİ bekliyorsunuz. Faiz düşüşü tahvil fiyatlarını "
            f"yükselttiği için durasyonu uzatmak (yaklaşık {hedef_durasyon:.1f} yıl) "
            f"kazancı büyütür. {ek}"
        )
    else:  # sabit
        hedef_durasyon = ufuk_yil
        if tolerans == "dusuk":
            strateji = "immünizasyon"
            ek = (
                "Durasyonu ufkunuza eşitleyen immünizasyon, küçük faiz oynamalarına "
                "karşı hedef birikiminizi korur; 'kur ve unut' yaklaşımına en yakın "
                "çözümdür."
            )
        elif tolerans == "orta":
            strateji = "merdiven"
            ek = (
                "Merdiven (ladder), vadeleri yayarak yeniden yatırım riskini "
                "dengeler, düzenli nakit akışı sağlar ve faiz tahmini gerektirmez; "
                "yatay seyirde en dengeli stratejidir."
            )
        else:
            strateji = "barbell"
            ek = (
                "Getiri eğrisi pozitif eğimliyse barbell (halter), uzun uçtan taşıma "
                "(carry) ve zamanla fiyatın eğri üzerinde kayması (roll-down) "
                "getirisini yakalarken kısa uç esneklik sağlar."
            )
        gerekce = (
            f"Faizlerin SABİT kalmasını bekliyorsunuz. Yön tahmini olmayan ortamda "
            f"getiri, kupon taşıması ve yeniden yatırım disiplininden gelir; "
            f"durasyonu yaklaşık ufkunuzda ({hedef_durasyon:.1f} yıl) tutmak "
            f"dengelidir. {ek}"
        )

    return StratejiOnerisi(strateji=strateji, hedef_durasyon=hedef_durasyon, gerekce=gerekce)
