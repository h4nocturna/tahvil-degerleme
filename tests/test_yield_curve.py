"""Getiri eğrisi testleri: bootstrap, forward, interpolasyon, Nelson-Siegel."""

from itertools import pairwise

import pytest

from bond_lab.bond import Tahvil
from bond_lab.pricing import spot_egriden_fiyat
from bond_lab.yield_curve import (
    GetiriEgrisi,
    nelson_siegel_orani,
    nelson_siegel_uydur,
)


def _par_enstrumanlar(par_getiriler: dict, frekans: int = 1):
    """Fiyatı 100 (par) olan kuponlu tahvil listesi üretir."""
    return [
        (Tahvil(nominal=100, kupon_orani=c, vade_yil=v, frekans=frekans), 100.0)
        for v, c in par_getiriler.items()
    ]


def test_bootstrap_gidis_donus_yillik():
    """Bootstrap eğrisinden fiyatlanan her girdi tahvili fiyatını geri vermeli."""
    par = {1: 0.36, 2: 0.33, 3: 0.305, 4: 0.285, 5: 0.27}
    enstrumanlar = _par_enstrumanlar(par)
    egri = GetiriEgrisi.bootstrap(enstrumanlar)
    for tahvil, fiyat in enstrumanlar:
        assert spot_egriden_fiyat(tahvil, egri) == pytest.approx(fiyat, abs=1e-8)


def test_bootstrap_gidis_donus_6aylik():
    """6 aylık kuponlu enstrümanlarla da gidiş-dönüş tutmalı."""
    par = {0.5: 0.10, 1.0: 0.11, 1.5: 0.115, 2.0: 0.12}
    enstrumanlar = _par_enstrumanlar(par, frekans=2)
    egri = GetiriEgrisi.bootstrap(enstrumanlar)
    for tahvil, fiyat in enstrumanlar:
        assert spot_egriden_fiyat(tahvil, egri) == pytest.approx(fiyat, abs=1e-8)


def test_bootstrap_spot_par_ustunde_artan_egri():
    """Artan eğride spot oranlar par getirilerin üstünde olmalı (klasik sonuç)."""
    par = {1: 0.05, 2: 0.06, 3: 0.07, 4: 0.08}
    egri = GetiriEgrisi.bootstrap(_par_enstrumanlar(par))
    for v in (2, 3, 4):
        assert egri.spot_oran(v) > par[v]


def test_duz_egri_forward_spota_esit():
    """Düz eğride tüm forward oranlar spot orana eşittir."""
    egri = GetiriEgrisi([1, 2, 5, 10], [0.08] * 4)
    assert egri.forward_oran(1, 2) == pytest.approx(0.08)
    assert egri.forward_oran(2, 7) == pytest.approx(0.08)


def test_forward_tutarlilik():
    """(1+z2)² = (1+z1)·(1+f_{1,2}) tutarlılığı sağlanmalı."""
    egri = GetiriEgrisi([1, 2], [0.05, 0.07])
    f12 = egri.forward_oran(1, 2)
    assert (1 + 0.05) * (1 + f12) == pytest.approx(1.07**2)


def test_interpolasyon_dugum_noktalarinda_kesin():
    """Doğrusal ve kübik interpolasyon düğüm noktalarında girdiyi vermeli."""
    vadeler, oranlar = [1, 3, 5, 10], [0.05, 0.06, 0.065, 0.07]
    for tur in ("dogrusal", "kubik"):
        egri = GetiriEgrisi(vadeler, oranlar, interpolasyon=tur)
        for v, o in zip(vadeler, oranlar, strict=True):
            assert egri.spot_oran(v) == pytest.approx(o, abs=1e-12)


def test_dogrusal_interpolasyon_orta_nokta():
    """Doğrusal interpolasyonda orta nokta aritmetik ortalama olmalı."""
    egri = GetiriEgrisi([1, 3], [0.04, 0.08])
    assert egri.spot_oran(2) == pytest.approx(0.06)


def test_duz_ekstrapolasyon():
    """Aralık dışı vadelerde uç oranlar (flat) kullanılmalı."""
    egri = GetiriEgrisi([1, 5], [0.05, 0.09])
    assert egri.spot_oran(0.25) == pytest.approx(0.05)
    assert egri.spot_oran(30) == pytest.approx(0.09)


def test_iskonto_faktoru_azalan_ve_sifirda_bir():
    """DF(0)=1 ve pozitif oranlarda DF vadeyle azalmalı."""
    egri = GetiriEgrisi([1, 2, 5, 10], [0.05, 0.06, 0.07, 0.075])
    assert egri.iskonto_faktoru(0) == pytest.approx(1.0)
    dfler = [egri.iskonto_faktoru(t) for t in (0.5, 1, 2, 5, 10)]
    assert all(a > b for a, b in pairwise(dfler))


def test_nelson_siegel_bilinen_egriyi_geri_bulur():
    """NS ile üretilen veriye NS uydurunca oranlar geri elde edilmeli."""
    b0, b1, b2, tau = 0.08, -0.03, 0.02, 2.0
    vadeler = [0.5, 1, 2, 3, 5, 7, 10, 20]
    oranlar = [nelson_siegel_orani(t, b0, b1, b2, tau) for t in vadeler]
    sonuc = nelson_siegel_uydur(vadeler, oranlar)
    assert sonuc.rmse < 1e-6
    for t in (0.75, 4, 15):
        assert sonuc.oran(t) == pytest.approx(nelson_siegel_orani(t, b0, b1, b2, tau), abs=1e-4)


def test_nelson_siegel_sifir_vade_limiti():
    """t→0 limitinde NS oranı beta0 + beta1 olmalı."""
    assert nelson_siegel_orani(0.0, 0.07, -0.02, 0.01, 1.5) == pytest.approx(0.05)


def test_gecersiz_egri_girdileri():
    """Uyumsuz uzunluk, tekrarlı vade ve geçersiz interpolasyon hata vermeli."""
    with pytest.raises(ValueError):
        GetiriEgrisi([1, 2], [0.05])
    with pytest.raises(ValueError):
        GetiriEgrisi([1, 1], [0.05, 0.06])
    with pytest.raises(ValueError):
        GetiriEgrisi([1, 2], [0.05, 0.06], interpolasyon="spline")
    with pytest.raises(ValueError):
        GetiriEgrisi([1, 2], [0.05, 0.06]).forward_oran(2, 1)
