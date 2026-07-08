"""Matplotlib görselleştirmeleri.

Tüm fonksiyonlar grafikleri PNG olarak ``output/`` klasörüne kaydeder ve
kaydedilen dosyanın yolunu döndürür. Ekrana pencere açılmaz (Agg backend);
bu sayede sunucu/konsol ortamlarında da sorunsuz çalışır.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # pencere açmadan dosyaya çizim

import matplotlib.pyplot as plt
import numpy as np

from bond_lab.bond import Tahvil
from bond_lab.portfolio import Portfoy
from bond_lab.pricing import kirli_fiyat
from bond_lab.yield_curve import GetiriEgrisi, NelsonSiegelSonuc

VARSAYILAN_KLASOR = Path("output")


def _hazirla(cikti_klasoru: Path | None) -> Path:
    """Çıktı klasörünü oluşturur ve Path olarak döndürür."""
    klasor = Path(cikti_klasoru) if cikti_klasoru is not None else VARSAYILAN_KLASOR
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def fiyat_getiri_grafigi(
    tahviller: Sequence[Tahvil],
    ytm_min: float = 0.01,
    ytm_maks: float = 0.60,
    dosya_adi: str = "fiyat_getiri.png",
    cikti_klasoru: Path | None = None,
) -> Path:
    """Fiyat–getiri eğrisi: verilen tahvillerin YTM'ye göre kirli fiyatı.

    Eğrinin dışbükeyliği (konveksite) görsel olarak burada izlenir.

    Raises:
        ValueError: Tahvil listesi boşsa.
    """
    if not tahviller:
        raise ValueError("Grafik için en az bir tahvil gereklidir.")
    klasor = _hazirla(cikti_klasoru)
    ytmler = np.linspace(ytm_min, ytm_maks, 200)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for tahvil in tahviller:
        fiyatlar = [kirli_fiyat(tahvil, float(y)) for y in ytmler]
        etiket = tahvil.isim or f"{tahvil.vade_yil:g}Y %{tahvil.kupon_orani * 100:.0f}"
        ax.plot(ytmler * 100, fiyatlar, label=etiket, linewidth=2)
    ax.set_xlabel("Vadeye Kadar Getiri — YTM (%)")
    ax.set_ylabel("Kirli Fiyat")
    ax.set_title("Fiyat–Getiri Eğrisi (dışbükeylik = konveksite)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    yol = klasor / dosya_adi
    fig.tight_layout()
    fig.savefig(yol, dpi=150)
    plt.close(fig)
    return yol


def getiri_egrisi_grafigi(
    egri: GetiriEgrisi,
    ns: NelsonSiegelSonuc | None = None,
    dosya_adi: str = "getiri_egrisi.png",
    cikti_klasoru: Path | None = None,
) -> Path:
    """Spot eğri, 1 yıllık forward oranlar ve opsiyonel Nelson-Siegel eğrisi."""
    klasor = _hazirla(cikti_klasoru)
    t_izgara = np.linspace(float(egri.vadeler[0]), float(egri.vadeler[-1]), 200)
    spotlar = [egri.spot_oran(float(t)) * 100 for t in t_izgara]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(t_izgara, spotlar, label="Spot eğri", linewidth=2)
    ax.scatter(
        egri.vadeler,
        egri.oranlar * 100,
        color="crimson",
        zorder=5,
        label="Bootstrap noktaları",
    )

    fwd_t = [float(t) for t in t_izgara if t + 1.0 <= float(egri.vadeler[-1])]
    if fwd_t:
        forwardlar = [egri.forward_oran(t, t + 1.0) * 100 for t in fwd_t]
        ax.plot(fwd_t, forwardlar, "--", label="1Y forward", linewidth=1.8)

    if ns is not None:
        ns_oranlar = [ns.oran(float(t)) * 100 for t in t_izgara]
        ax.plot(t_izgara, ns_oranlar, ":", label="Nelson-Siegel", linewidth=2)

    ax.set_xlabel("Vade (yıl)")
    ax.set_ylabel("Oran (%)")
    ax.set_title("Getiri Eğrisi: Spot / Forward / Nelson-Siegel")
    ax.legend()
    ax.grid(True, alpha=0.3)
    yol = klasor / dosya_adi
    fig.tight_layout()
    fig.savefig(yol, dpi=150)
    plt.close(fig)
    return yol


def strateji_karsilastirma_grafigi(
    sonuclar: dict[str, dict[str, dict[str, float]]],
    dosya_adi: str = "strateji_karsilastirma.png",
    cikti_klasoru: Path | None = None,
) -> Path:
    """Senaryo bazlı strateji karşılaştırması (gruplu bar grafiği).

    Args:
        sonuclar: ``{strateji_adi: {senaryo_adi: {"degisim_yuzde": ...}}}``
            biçiminde, :func:`bond_lab.strategies.senaryo_analizi`
            çıktılarının strateji adına göre sözlüğü.

    Raises:
        ValueError: Sonuç sözlüğü boşsa.
    """
    if not sonuclar:
        raise ValueError("Grafik için en az bir strateji sonucu gereklidir.")
    klasor = _hazirla(cikti_klasoru)
    stratejiler = list(sonuclar.keys())
    senaryolar = list(next(iter(sonuclar.values())).keys())
    x = np.arange(len(senaryolar))
    genislik = 0.8 / max(len(stratejiler), 1)

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, strateji in enumerate(stratejiler):
        degerler = [sonuclar[strateji][s]["degisim_yuzde"] for s in senaryolar]
        ax.bar(x + i * genislik, degerler, genislik, label=strateji)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x + genislik * (len(stratejiler) - 1) / 2)
    ax.set_xticklabels(senaryolar, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Portföy değer değişimi (%)")
    ax.set_title("Faiz Senaryoları Altında Strateji Karşılaştırması")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    yol = klasor / dosya_adi
    fig.tight_layout()
    fig.savefig(yol, dpi=150)
    plt.close(fig)
    return yol


def nakit_akisi_grafigi(
    portfoyler: Sequence[Portfoy],
    dosya_adi: str = "nakit_akisi.png",
    cikti_klasoru: Path | None = None,
) -> Path:
    """Portföylerin nakit akışı zaman çizelgesi (yıl bazında yığın bar).

    Raises:
        ValueError: Portföy listesi boşsa.
    """
    if not portfoyler:
        raise ValueError("Grafik için en az bir portföy gereklidir.")
    klasor = _hazirla(cikti_klasoru)
    fig, eksenler = plt.subplots(
        len(portfoyler),
        1,
        figsize=(10, 3.2 * len(portfoyler)),
        sharex=True,
        squeeze=False,
    )
    for ax, portfoy in zip(eksenler[:, 0], portfoyler, strict=True):
        takvim = portfoy.nakit_akisi_takvimi()
        zamanlar = [t for t, _ in takvim]
        tutarlar = [cf for _, cf in takvim]
        ax.bar(zamanlar, tutarlar, width=0.35, color="steelblue")
        ax.set_title(f"{portfoy.isim} — nakit akışı takvimi")
        ax.set_ylabel("Tutar")
        ax.grid(True, axis="y", alpha=0.3)
    eksenler[-1, 0].set_xlabel("Zaman (yıl)")
    yol = klasor / dosya_adi
    fig.tight_layout()
    fig.savefig(yol, dpi=150)
    plt.close(fig)
    return yol
