"""Fiyatlama fonksiyonları testleri: fiyat, YTM, spot eğri, cari getiri."""

from itertools import pairwise

import pytest

from bond_lab.bond import Tahvil
from bond_lab.pricing import (
    cari_getiri,
    kirli_fiyat,
    spot_egriden_fiyat,
    temiz_fiyat,
    ytm_bul,
)
from bond_lab.yield_curve import GetiriEgrisi


def test_par_tahvil_fiyati_nominale_esit_yillik():
    """Kupon oranı = YTM iken fiyat nominal olmalı (yıllık kupon)."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
    assert kirli_fiyat(tahvil, 0.10) == pytest.approx(100.0, abs=1e-10)


def test_par_tahvil_fiyati_nominale_esit_6aylik():
    """Par kuralı 6 aylık kuponda da geçerli: dönemsel kupon = dönemsel getiri."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.12, vade_yil=7, frekans=2)
    assert kirli_fiyat(tahvil, 0.12) == pytest.approx(100.0, abs=1e-10)


def test_sifir_kuponlu_fiyat_formulu():
    """Sıfır kuponlu fiyat = N / (1+y/f)^(f·T) kapalı formülüne eşit olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.0, vade_yil=10, frekans=1)
    assert kirli_fiyat(tahvil, 0.13) == pytest.approx(100 / 1.13**10)
    tahvil2 = Tahvil(nominal=100, kupon_orani=0.0, vade_yil=4, frekans=2)
    assert kirli_fiyat(tahvil2, 0.08) == pytest.approx(100 / 1.04**8)


def test_iskonto_ve_prim_iliskisi():
    """YTM > kupon → iskonto (fiyat < nominal); YTM < kupon → prim."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
    assert kirli_fiyat(tahvil, 0.12) < 100.0
    assert kirli_fiyat(tahvil, 0.08) > 100.0


def test_fiyat_getiride_azalan():
    """Fiyat, getirinin kesin azalan fonksiyonu olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=8, frekans=2)
    fiyatlar = [kirli_fiyat(tahvil, y) for y in (0.02, 0.06, 0.10, 0.20, 0.40)]
    assert all(a > b for a, b in pairwise(fiyatlar))


@pytest.mark.parametrize(
    "kupon, vade, frekans, ytm",
    [
        (0.10, 5, 1, 0.12),
        (0.12, 7, 2, 0.09),
        (0.0, 10, 1, 0.25),
        (0.35, 2, 4, 0.42),
        (0.10, 4.75, 1, 0.15),  # kesirli vade + işlemiş faiz
    ],
)
def test_ytm_fiyat_gidis_donus(kupon, vade, frekans, ytm):
    """YTM→fiyat→YTM gidiş-dönüşü başlangıç getirisini geri vermeli."""
    tahvil = Tahvil(nominal=100, kupon_orani=kupon, vade_yil=vade, frekans=frekans)
    fiyat = temiz_fiyat(tahvil, ytm)
    assert ytm_bul(tahvil, fiyat, temiz=True) == pytest.approx(ytm, abs=1e-8)


def test_ytm_bul_kotu_baslangicta_bisection_yedegi():
    """Newton kötü başlangıçta bile bisection sayesinde doğru kök bulunmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.40, vade_yil=1, frekans=1)
    fiyat = kirli_fiyat(tahvil, 3.0)  # %300 getiri gibi uç bir durum
    assert ytm_bul(tahvil, fiyat, temiz=False, tahmin=0.01) == pytest.approx(3.0, abs=1e-6)


def test_temiz_kirli_fiyat_farki_islemis_faiz():
    """Kirli − temiz fiyat farkı tam olarak işlemiş faize eşit olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=4.75, frekans=1)
    ytm = 0.12
    assert kirli_fiyat(tahvil, ytm) - temiz_fiyat(tahvil, ytm) == pytest.approx(
        tahvil.islemis_faiz()
    )
    assert tahvil.islemis_faiz() > 0.0


def test_cari_getiri():
    """Cari getiri = yıllık kupon / temiz fiyat; sıfır kuponluda 0."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
    assert cari_getiri(tahvil, 95.0) == pytest.approx(10.0 / 95.0)
    sifir = Tahvil(nominal=100, kupon_orani=0.0, vade_yil=5, frekans=1)
    assert cari_getiri(sifir, 60.0) == 0.0
    with pytest.raises(ValueError):
        cari_getiri(tahvil, 0.0)


def test_duz_spot_egriden_fiyat_ytm_fiyatina_esit():
    """Düz (flat) spot eğriden fiyat, aynı orandaki YTM fiyatına eşit olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
    duz = GetiriEgrisi([1, 2, 3, 4, 5], [0.11] * 5)
    assert spot_egriden_fiyat(tahvil, duz) == pytest.approx(kirli_fiyat(tahvil, 0.11))


def test_gecersiz_fiyat_hata_verir():
    """Pozitif olmayan fiyat için YTM çözümü hata vermeli."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
    with pytest.raises(ValueError):
        ytm_bul(tahvil, -5.0)
