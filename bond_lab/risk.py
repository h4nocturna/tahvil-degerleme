"""Faiz riski ölçütleri: durasyon, konveksite ve türevleri.

Tanımlar (yıllık YTM ``y``, frekans ``f``, kirli fiyat ``P``):
    * Macaulay durasyonu: nakit akışlarının bugünkü değer ağırlıklı
      ortalama vadesi (yıl), ``D_mac = Σ t·PV(t) / P``.
    * Modifiye durasyon: ``D_mod = D_mac / (1 + y/f)``;
      fiyatın getiriye yüzde duyarlılığı, ``D_mod ≈ -(1/P)·dP/dy``.
    * Dolar durasyon: ``DD = D_mod · P`` (1.00'lık, yani 100 puanlık getiri
      değişimi başına fiyat değişimi).
    * DV01 / PVBP: 1 baz puanlık (0.0001) getiri değişiminin fiyat etkisi,
      ``DV01 = DD · 0.0001``.
    * Konveksite: ``C = (1/P)·d²P/dy²``; durasyon tahminini iyileştirir.

İkinci mertebe fiyat değişimi tahmini:
    ``ΔP ≈ P·(-D_mod·Δy + 0.5·C·Δy²)``.
"""

from __future__ import annotations

from bond_lab.bond import Tahvil
from bond_lab.pricing import kirli_fiyat


def macaulay_durasyon(tahvil: Tahvil, ytm: float) -> float:
    """Macaulay durasyonu (yıl): PV ağırlıklı ortalama nakit akışı vadesi."""
    f = tahvil.frekans
    d = ytm / f
    fiyat = kirli_fiyat(tahvil, ytm)
    agirlikli_toplam = sum(t * cf * (1.0 + d) ** (-(f * t)) for t, cf in tahvil.nakit_akislari())
    return agirlikli_toplam / fiyat


def modifiye_durasyon(tahvil: Tahvil, ytm: float) -> float:
    """Modifiye durasyon = Macaulay / (1 + ytm/frekans)."""
    return macaulay_durasyon(tahvil, ytm) / (1.0 + ytm / tahvil.frekans)


def dolar_durasyon(tahvil: Tahvil, ytm: float) -> float:
    """Dolar (parasal) durasyon = modifiye durasyon × kirli fiyat.

    Getirideki 1.00'lık (yüzde 100 puanlık) değişim başına yaklaşık fiyat
    değişimidir; pratikte DV01'e temel oluşturur.
    """
    return modifiye_durasyon(tahvil, ytm) * kirli_fiyat(tahvil, ytm)


def dv01(tahvil: Tahvil, ytm: float) -> float:
    """DV01 (PVBP): 1 baz puanlık getiri artışının yaklaşık fiyat etkisi."""
    return dolar_durasyon(tahvil, ytm) * 1e-4


def konveksite(tahvil: Tahvil, ytm: float) -> float:
    """Konveksite (yıl²): C = (1/P)·d²P/dy².

    Dönemsel gösterimle (n = f·t dönem sayısı, d = y/f dönemsel getiri):
    ``C = Σ CF·n·(n+1)·(1+d)^-(n+2) / (P·f²)``.
    """
    f = tahvil.frekans
    d = ytm / f
    fiyat = kirli_fiyat(tahvil, ytm)
    toplam = sum(
        cf * (f * t) * (f * t + 1.0) * (1.0 + d) ** (-(f * t) - 2.0)
        for t, cf in tahvil.nakit_akislari()
    )
    return toplam / (fiyat * f * f)


def fiyat_degisim_tahmini(
    tahvil: Tahvil,
    ytm: float,
    delta_y: float,
    konveksite_dahil: bool = True,
) -> float:
    """Durasyon (+ opsiyonel konveksite) ile yaklaşık fiyat değişimi (ΔP).

    ``ΔP ≈ P·(-D_mod·Δy + 0.5·C·Δy²)`` — konveksite_dahil False ise yalnızca
    birinci terim kullanılır.

    Args:
        tahvil: Tahvil.
        ytm: Mevcut yıllık getiri.
        delta_y: Getiri değişimi (ondalık; +0.01 = +100bp).
        konveksite_dahil: İkinci mertebe düzeltme eklensin mi?

    Returns:
        Yaklaşık kirli fiyat değişimi (nominal birimiyle).
    """
    fiyat = kirli_fiyat(tahvil, ytm)
    tahmin = -modifiye_durasyon(tahvil, ytm) * fiyat * delta_y
    if konveksite_dahil:
        tahmin += 0.5 * konveksite(tahvil, ytm) * fiyat * delta_y * delta_y
    return tahmin


def fiyat_degisim_karsilastir(tahvil: Tahvil, ytm: float, delta_y: float) -> dict[str, float]:
    """Tahmin edilen ve gerçek fiyat değişimini karşılaştırır.

    Gerçek değişim, tahvilin ``ytm + delta_y`` getirisiyle yeniden
    fiyatlanmasıyla bulunur; tahminler durasyon ve durasyon+konveksite
    yaklaşımlarıdır.

    Returns:
        Sözlük anahtarları:
            ``gercek_degisim``, ``tahmin_durasyon``,
            ``tahmin_durasyon_konveksite``, ``mutlak_hata_durasyon``,
            ``mutlak_hata_durasyon_konveksite``.
    """
    fiyat_0 = kirli_fiyat(tahvil, ytm)
    fiyat_1 = kirli_fiyat(tahvil, ytm + delta_y)
    gercek = fiyat_1 - fiyat_0
    t_dur = fiyat_degisim_tahmini(tahvil, ytm, delta_y, konveksite_dahil=False)
    t_dur_konv = fiyat_degisim_tahmini(tahvil, ytm, delta_y, konveksite_dahil=True)
    return {
        "gercek_degisim": gercek,
        "tahmin_durasyon": t_dur,
        "tahmin_durasyon_konveksite": t_dur_konv,
        "mutlak_hata_durasyon": abs(t_dur - gercek),
        "mutlak_hata_durasyon_konveksite": abs(t_dur_konv - gercek),
    }
