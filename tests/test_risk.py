"""Durasyon, konveksite ve DV01 testleri (bilinen değerlerle karşılaştırmalı)."""

import pytest

from bond_lab.bond import Tahvil
from bond_lab.pricing import kirli_fiyat
from bond_lab.risk import (
    dolar_durasyon,
    dv01,
    fiyat_degisim_karsilastir,
    fiyat_degisim_tahmini,
    konveksite,
    macaulay_durasyon,
    modifiye_durasyon,
)


def test_sifir_kuponlu_macaulay_vadeye_esit():
    """Sıfır kuponlu tahvilin Macaulay durasyonu vadesine eşittir."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.0, vade_yil=8, frekans=1)
    assert macaulay_durasyon(tahvil, 0.15) == pytest.approx(8.0)
    tahvil2 = Tahvil(nominal=100, kupon_orani=0.0, vade_yil=8, frekans=2)
    assert macaulay_durasyon(tahvil2, 0.15) == pytest.approx(8.0)


def test_modifiye_durasyon_tanimi():
    """Modifiye durasyon = Macaulay / (1 + ytm/frekans)."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.12, vade_yil=6, frekans=2)
    ytm = 0.10
    assert modifiye_durasyon(tahvil, ytm) == pytest.approx(macaulay_durasyon(tahvil, ytm) / 1.05)


def test_bilinen_deger_2y_yillik_kupon():
    """2Y %10 kuponlu, YTM %10: D_mac = (1·PV1 + 2·PV2)/P elle hesaplanır.

    PV1 = 10/1.1 = 9.0909..., PV2 = 110/1.21 = 90.9090..., P = 100
    D_mac = (9.0909 + 2·90.9090)/100 = 1.909090...
    """
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=2, frekans=1)
    assert macaulay_durasyon(tahvil, 0.10) == pytest.approx(21 / 11, abs=1e-12)


def test_kuponlu_durasyon_vadeden_kisa():
    """Kuponlu tahvilin durasyonu vadesinden kısa olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=10, frekans=1)
    assert macaulay_durasyon(tahvil, 0.10) < 10.0


def test_kupon_arttikca_durasyon_azalir():
    """Aynı vade ve getiride kupon oranı arttıkça durasyon azalmalı."""
    ytm = 0.10
    d_dusuk = macaulay_durasyon(Tahvil(100, 0.05, 10, 1), ytm)
    d_yuksek = macaulay_durasyon(Tahvil(100, 0.15, 10, 1), ytm)
    assert d_yuksek < d_dusuk


def test_dv01_sonlu_farka_yakin():
    """DV01, merkezi sonlu fark tahminine çok yakın olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.12, vade_yil=7, frekans=2)
    ytm = 0.11
    bp = 1e-4
    sonlu_fark = (kirli_fiyat(tahvil, ytm - bp) - kirli_fiyat(tahvil, ytm + bp)) / 2
    assert dv01(tahvil, ytm) == pytest.approx(sonlu_fark, rel=1e-4)


def test_dolar_durasyon_tanimi():
    """Dolar durasyon = modifiye durasyon × kirli fiyat."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
    ytm = 0.12
    assert dolar_durasyon(tahvil, ytm) == pytest.approx(
        modifiye_durasyon(tahvil, ytm) * kirli_fiyat(tahvil, ytm)
    )


def test_sifir_kuponlu_konveksite_kapali_formul():
    """Yıllık bileşikte sıfır kuponlu konveksite = T(T+1)/(1+y)²."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.0, vade_yil=6, frekans=1)
    y = 0.09
    assert konveksite(tahvil, y) == pytest.approx(6 * 7 / 1.09**2, abs=1e-10)


def test_konveksite_ikinci_turev_sonlu_farka_yakin():
    """Konveksite, ikinci türevin sonlu fark tahminiyle uyuşmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=10, frekans=2)
    y, h = 0.12, 1e-5
    p0 = kirli_fiyat(tahvil, y)
    ikinci_turev = (kirli_fiyat(tahvil, y + h) - 2 * p0 + kirli_fiyat(tahvil, y - h)) / h**2
    assert konveksite(tahvil, y) == pytest.approx(ikinci_turev / p0, rel=1e-4)


def test_konveksite_duzeltmesi_tahmini_iyilestirir():
    """±200bp şokta dur+konv tahmininin hatası salt durasyondan küçük olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=10, frekans=1)
    for delta in (0.02, -0.02):
        k = fiyat_degisim_karsilastir(tahvil, 0.12, delta)
        assert k["mutlak_hata_durasyon_konveksite"] < k["mutlak_hata_durasyon"]


def test_fiyat_degisim_tahmini_isaretleri():
    """Faiz artınca tahmini değişim negatif, düşünce pozitif olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
    assert fiyat_degisim_tahmini(tahvil, 0.10, +0.01) < 0
    assert fiyat_degisim_tahmini(tahvil, 0.10, -0.01) > 0
