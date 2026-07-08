"""Strateji backtest/simülasyon motoru.

Belirli bir yatırım ufkunda merdiven (ladder), barbell (halter) ve bullet
(mermi) stratejilerinin TOPLAM getirisini karşılaştırır. İki faiz ortamı
üretici desteklenir:

    * :func:`deterministik_patikalar` — kademeli artış/düşüş, sabit ve
      anlık şok senaryoları (paralel kayma patikaları).
    * :func:`vasicek_patikalari` — Vasicek kısa vade modeliyle stokastik
      simülasyon (``dr = a(b−r)dt + σ dW``; tekrarlanabilirlik için seed).

Backtest mekaniği (bilinçli basitleştirmelerle):
    * Faiz ortamı, başlangıç eğrisine uygulanan PARALEL kayma patikasıdır.
    * Kuponlar ve vadesi gelen anaparalar nakit hesabına aktarılır; nakit
      her adımda o anki kısa vadeli oranla (başlangıç kısa ucu + kayma)
      bileşik olarak nemalandırılır (kupon reinvest).
    * Ufuk sonunda vadesi geçmemiş tahviller, kalan vadeleriyle ve
      ``başlangıç YTM + ufuktaki kayma`` getirisiyle yeniden fiyatlanır
      (basitleştirilmiş yeniden fiyatlama; eğri üzerinde kayma/roll-down
      ihmal edilir).

Çıktılar: strateji × patika toplam/yıllık getiri tabloları, Vasicek
dağılım özeti (ortalama, std, min, maks) ve karşılaştırma grafiği
(``output/`` klasörüne PNG, Agg backend).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # pencere açmadan dosyaya çizim

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bond_lab.bond import Tahvil
from bond_lab.portfolio import Portfoy
from bond_lab.pricing import kirli_fiyat
from bond_lab.strategies import barbell_portfoy, bullet_portfoy, merdiven_portfoy
from bond_lab.yield_curve import GetiriEgrisi

VARSAYILAN_CIKTI = Path("output")

#: Vasicek parametreleri için makul varsayılanlar (yıllık).
VASICEK_VARSAYILAN = {"a": 0.30, "sigma": 0.015}


# ----------------------------------------------------------------------
# Faiz patikaları
# ----------------------------------------------------------------------
def deterministik_patikalar(
    ufuk_yil: float, adim_sayisi: int, toplam_bp: float = 300.0
) -> dict[str, np.ndarray]:
    """Standart deterministik kayma patikaları üretir.

    Her patika, ``adim_sayisi + 1`` noktalı (t=0 dahil) PARALEL kayma
    dizisidir (ondalık). t=0'da kayma 0'dır (portföy kurulur), sonra
    patika işler.

    Patikalar:
        * ``Sabit`` — kayma yok.
        * ``Kademeli artış`` — ufuk boyunca doğrusal olarak +toplam_bp'ye.
        * ``Kademeli düşüş`` — doğrusal olarak −toplam_bp'ye.
        * ``Ani şok +200bp`` / ``Ani şok −200bp`` — ilk adımda tam şok,
          sonra sabit.

    Args:
        ufuk_yil: Backtest ufku (yıl), yalnızca doğrulama için.
        adim_sayisi: Zaman adımı sayısı (>=1).
        toplam_bp: Kademeli patikaların ufuk sonundaki büyüklüğü (baz puan).

    Raises:
        ValueError: adim_sayisi < 1 veya ufuk_yil <= 0 ise.
    """
    if ufuk_yil <= 0:
        raise ValueError("Ufuk pozitif olmalıdır.")
    if adim_sayisi < 1:
        raise ValueError("En az bir zaman adımı gereklidir.")
    n = adim_sayisi
    dogrusal = np.linspace(0.0, toplam_bp / 10000.0, n + 1)
    sok_yukari = np.full(n + 1, 200.0 / 10000.0)
    sok_yukari[0] = 0.0
    sok_asagi = -sok_yukari
    return {
        "Sabit": np.zeros(n + 1),
        f"Kademeli artış (+{toplam_bp:.0f}bp)": dogrusal,
        f"Kademeli düşüş (−{toplam_bp:.0f}bp)": -dogrusal,
        "Ani şok +200bp": sok_yukari,
        "Ani şok −200bp": sok_asagi,
    }


def vasicek_patikalari(
    r0: float,
    ufuk_yil: float,
    adim_sayisi: int,
    patika_sayisi: int = 200,
    a: float = VASICEK_VARSAYILAN["a"],
    b: float | None = None,
    sigma: float = VASICEK_VARSAYILAN["sigma"],
    seed: int = 42,
) -> np.ndarray:
    """Vasicek modeliyle kısa vadeli oran patikaları simüle eder.

    Model: ``dr = a(b − r)dt + σ dW`` (Euler ayrıklaştırması). Oranların
    aşırı negatife düşmesi ekonomik olarak anlamsız fiyatlar üretmesin
    diye patikalar −%2 ile kırpılır (Vasicek negatif orana izin verir;
    kırpma yalnızca uç durumları sınırlar).

    Args:
        r0: Başlangıç kısa vadeli oranı (ondalık).
        ufuk_yil: Simülasyon ufku (yıl).
        adim_sayisi: Zaman adımı sayısı.
        patika_sayisi: Simüle edilecek patika adedi.
        a: Ortalamaya dönüş hızı (>0).
        b: Uzun dönem ortalama; None ise r0 alınır.
        sigma: Yıllık oynaklık (>=0).
        seed: RNG tohumu (tekrarlanabilirlik).

    Returns:
        ``(patika_sayisi, adim_sayisi + 1)`` boyutlu ORAN SEVİYESİ dizisi
        (kayma değil); ilk sütun r0'dır.

    Raises:
        ValueError: Parametreler geçersizse.
    """
    if a <= 0 or sigma < 0 or ufuk_yil <= 0 or adim_sayisi < 1 or patika_sayisi < 1:
        raise ValueError("Vasicek parametreleri geçersiz.")
    hedef = r0 if b is None else b
    dt = ufuk_yil / adim_sayisi
    rng = np.random.default_rng(seed)
    r = np.empty((patika_sayisi, adim_sayisi + 1))
    r[:, 0] = r0
    kok_dt = np.sqrt(dt)
    for i in range(adim_sayisi):
        dw = rng.standard_normal(patika_sayisi) * kok_dt
        r[:, i + 1] = r[:, i] + a * (hedef - r[:, i]) * dt + sigma * dw
    return np.maximum(r, -0.02)


# ----------------------------------------------------------------------
# Tek portföy, tek patika backtest'i
# ----------------------------------------------------------------------
def portfoy_backtest(
    portfoy: Portfoy,
    kaymalar: Sequence[float] | np.ndarray,
    zamanlar: Sequence[float] | np.ndarray,
    kisa_oran0: float,
) -> float:
    """Portföyün verilen kayma patikası altında ufuk sonu TOPLAM getirisi.

    Args:
        portfoy: t=0'da kurulmuş portföy (pozisyon YTM'leri başlangıç
            değerlemesidir).
        kaymalar: Zaman ızgarasındaki paralel kayma değerleri (ondalık);
            ``len(kaymalar) == len(zamanlar)`` ve ``kaymalar[0] == 0``
            beklenir (t=0'da kayma yok).
        zamanlar: Artan zaman ızgarası, ``zamanlar[0] == 0`` ve son eleman
            ufuk T'dir.
        kisa_oran0: Başlangıç kısa vadeli oranı (nakit nema tabanı).

    Returns:
        Toplam getiri, ondalık (0.25 = %25).

    Raises:
        ValueError: Izgara uzunlukları tutmuyorsa.
    """
    if len(kaymalar) != len(zamanlar):
        raise ValueError("kaymalar ve zamanlar aynı uzunlukta olmalıdır.")
    if len(zamanlar) < 2:
        raise ValueError("En az iki zaman noktası gereklidir.")
    ufuk = float(zamanlar[-1])
    baslangic = portfoy.toplam_deger
    if baslangic <= 0:
        raise ValueError("Başlangıç portföy değeri pozitif olmalıdır.")

    # Ufka kadar düşen tüm akışları (zaman, tutar) olarak topla.
    akislar: list[tuple[float, float]] = []
    for poz in portfoy.pozisyonlar:
        for t, cf in poz.tahvil.nakit_akislari():
            if t <= ufuk + 1e-9:
                akislar.append((t, cf * poz.adet))
    akislar.sort(key=lambda x: x[0])

    # Nakit hesabı: her adımda kısa oranla nemalanır, adım içindeki
    # akışlar adım SONUNDA eklenir (adım içi nema ihmali).
    nakit = 0.0
    akis_i = 0
    for i in range(len(zamanlar) - 1):
        t0, t1 = float(zamanlar[i]), float(zamanlar[i + 1])
        dt = t1 - t0
        oran = max(kisa_oran0 + float(kaymalar[i]), -0.02)
        nakit *= (1.0 + oran) ** dt
        while akis_i < len(akislar) and akislar[akis_i][0] <= t1 + 1e-9:
            nakit += akislar[akis_i][1]
            akis_i += 1

    # Ufuk sonunda kalan tahvilleri basitleştirilmiş kurala göre fiyatla.
    son_kayma = float(kaymalar[-1])
    tahvil_degeri = 0.0
    for poz in portfoy.pozisyonlar:
        kalan = poz.tahvil.vade_yil - ufuk
        if kalan <= 1e-9:
            continue  # anapara zaten nakit hesabına düştü
        kalan_tahvil = Tahvil(
            nominal=poz.tahvil.nominal,
            kupon_orani=poz.tahvil.kupon_orani,
            vade_yil=kalan,
            frekans=poz.tahvil.frekans,
            isim=poz.tahvil.isim,
        )
        yeni_ytm = poz.ytm + son_kayma
        tahvil_degeri += poz.adet * kirli_fiyat(kalan_tahvil, yeni_ytm)

    return (nakit + tahvil_degeri) / baslangic - 1.0


# ----------------------------------------------------------------------
# Strateji karşılaştırma motoru
# ----------------------------------------------------------------------
@dataclass
class BacktestKarsilastirma:
    """Backtest karşılaştırma çıktısı.

    Attributes:
        deterministik: Satır=patika, sütun=strateji; YILLIK getiri (%).
        stokastik_ozet: Vasicek dağılım özeti; satır=strateji,
            sütunlar: Ortalama %, Std %, Min %, Maks % (yıllık getiri).
        stokastik_ham: Strateji → yıllık getiri (%) dizisi (patika başına).
        ufuk_yil: Kullanılan ufuk.
        parametreler: Kullanılan simülasyon parametreleri (özet metin).
    """

    deterministik: pd.DataFrame
    stokastik_ozet: pd.DataFrame
    stokastik_ham: dict[str, np.ndarray]
    ufuk_yil: float
    parametreler: str


def _standart_portfoyler(egri: GetiriEgrisi, tutar: float, frekans: int = 1) -> dict[str, Portfoy]:
    """Karşılaştırmada kullanılan üç standart portföyü kurar.

    Merdiven 1..10 yıl basamakları, barbell 2Y+10Y (50/50), bullet 10Y
    (uzun durasyon — faiz artışına duyarlılığı belirgin olsun diye).
    """
    return {
        "Merdiven": merdiven_portfoy(tutar, list(range(1, 11)), egri, frekans=frekans),
        "Barbell": barbell_portfoy(tutar, kisa_vade=2, uzun_vade=10, getiri=egri, frekans=frekans),
        "Bullet": bullet_portfoy(tutar, hedef_vade=10, getiri=egri, frekans=frekans),
    }


def yillik_getiri(toplam: float, ufuk_yil: float) -> float:
    """Toplam getiriden yıllık bileşik getiri: ``(1+g)^(1/T) − 1``."""
    if ufuk_yil <= 0:
        raise ValueError("Ufuk pozitif olmalıdır.")
    return (1.0 + toplam) ** (1.0 / ufuk_yil) - 1.0


def stratejileri_backtest_et(
    egri: GetiriEgrisi,
    ufuk_yil: float = 3.0,
    tutar: float = 1_000_000.0,
    adim_sayisi: int | None = None,
    patika_sayisi: int = 200,
    seed: int = 42,
    portfoyler: dict[str, Portfoy] | None = None,
) -> BacktestKarsilastirma:
    """Üç stratejiyi deterministik ve stokastik patikalarda karşılaştırır.

    Args:
        egri: Başlangıç spot getiri eğrisi (portföyler buna göre kurulur).
        ufuk_yil: Backtest ufku (yıl).
        tutar: Her stratejiye yatırılan tutar.
        adim_sayisi: Zaman adımı; None ise çeyreklik (4 × ufuk, en az 4).
        patika_sayisi: Vasicek patika adedi.
        seed: Vasicek RNG tohumu.
        portfoyler: İsim→portföy; None ise standart merdiven/barbell/bullet.

    Returns:
        :class:`BacktestKarsilastirma` (tablolar + ham dağılım).
    """
    if adim_sayisi is None:
        adim_sayisi = max(int(round(4 * ufuk_yil)), 4)
    zamanlar = np.linspace(0.0, ufuk_yil, adim_sayisi + 1)
    kisa_oran0 = egri.spot_oran(min(1.0, float(egri.vadeler[0])))
    if portfoyler is None:
        portfoyler = _standart_portfoyler(egri, tutar)

    # --- Deterministik patikalar ---
    patikalar = deterministik_patikalar(ufuk_yil, adim_sayisi)
    det_satirlar: dict[str, dict[str, float]] = {}
    for patika_adi, kaymalar in patikalar.items():
        det_satirlar[patika_adi] = {
            strateji: yillik_getiri(portfoy_backtest(p, kaymalar, zamanlar, kisa_oran0), ufuk_yil)
            * 100.0
            for strateji, p in portfoyler.items()
        }
    deterministik = pd.DataFrame(det_satirlar).T
    deterministik.index.name = "Patika"

    # --- Vasicek stokastik simülasyon ---
    oran_patikalari = vasicek_patikalari(
        r0=kisa_oran0,
        ufuk_yil=ufuk_yil,
        adim_sayisi=adim_sayisi,
        patika_sayisi=patika_sayisi,
        seed=seed,
    )
    kayma_patikalari = oran_patikalari - kisa_oran0  # seviye → paralel kayma
    ham: dict[str, np.ndarray] = {}
    for strateji, p in portfoyler.items():
        getiriler = (
            np.array(
                [
                    yillik_getiri(
                        portfoy_backtest(p, kayma_patikalari[j], zamanlar, kisa_oran0),
                        ufuk_yil,
                    )
                    for j in range(kayma_patikalari.shape[0])
                ]
            )
            * 100.0
        )
        ham[strateji] = getiriler

    ozet = pd.DataFrame(
        {
            "Ortalama %": {s: float(np.mean(g)) for s, g in ham.items()},
            "Std %": {s: float(np.std(g, ddof=1)) for s, g in ham.items()},
            "Min %": {s: float(np.min(g)) for s, g in ham.items()},
            "Maks %": {s: float(np.max(g)) for s, g in ham.items()},
        }
    )
    ozet.index.name = "Strateji"

    parametreler = (
        f"ufuk={ufuk_yil:g} yıl, adım={adim_sayisi}, Vasicek: "
        f"a={VASICEK_VARSAYILAN['a']:g}, σ={VASICEK_VARSAYILAN['sigma']:g}, "
        f"r0=%{kisa_oran0 * 100:.2f}, patika={patika_sayisi}, seed={seed}"
    )
    return BacktestKarsilastirma(
        deterministik=deterministik,
        stokastik_ozet=ozet,
        stokastik_ham=ham,
        ufuk_yil=ufuk_yil,
        parametreler=parametreler,
    )


# ----------------------------------------------------------------------
# Grafik
# ----------------------------------------------------------------------
def backtest_grafigi(
    sonuc: BacktestKarsilastirma,
    dosya_adi: str = "backtest_karsilastirma.png",
    cikti_klasoru: Path | None = None,
) -> Path:
    """Backtest karşılaştırma grafiği (PNG).

    Sol panel: deterministik patikalarda yıllık getiri (gruplu bar).
    Sağ panel: Vasicek simülasyonunda yıllık getiri dağılımı (kutu grafiği).
    """
    klasor = Path(cikti_klasoru) if cikti_klasoru is not None else VARSAYILAN_CIKTI
    klasor.mkdir(parents=True, exist_ok=True)

    fig, (sol, sag) = plt.subplots(1, 2, figsize=(14, 6))

    df = sonuc.deterministik
    x = np.arange(len(df.index))
    genislik = 0.8 / max(len(df.columns), 1)
    for i, strateji in enumerate(df.columns):
        sol.bar(x + i * genislik, df[strateji].to_numpy(), genislik, label=strateji)
    sol.axhline(0, color="black", linewidth=0.8)
    sol.set_xticks(x + genislik * (len(df.columns) - 1) / 2)
    sol.set_xticklabels(df.index, rotation=20, ha="right", fontsize=9)
    sol.set_ylabel("Yıllık getiri (%)")
    sol.set_title(f"Deterministik patikalar (ufuk {sonuc.ufuk_yil:g} yıl)")
    sol.legend()
    sol.grid(True, axis="y", alpha=0.3)

    adlar = list(sonuc.stokastik_ham.keys())
    sag.boxplot([sonuc.stokastik_ham[s] for s in adlar], showmeans=True)
    sag.set_xticks(range(1, len(adlar) + 1))
    sag.set_xticklabels(adlar)
    sag.set_ylabel("Yıllık getiri (%)")
    sag.set_title("Vasicek simülasyonu — getiri dağılımı")
    sag.grid(True, axis="y", alpha=0.3)

    fig.suptitle("Strateji Backtest Karşılaştırması", fontsize=13)
    yol = klasor / dosya_adi
    fig.tight_layout()
    fig.savefig(yol, dpi=150)
    plt.close(fig)
    return yol
