"""Portföy testleri: değer, ağırlıklar, ağırlıklı ölçütler, nakit akışı."""

import pytest

from bond_lab.bond import Tahvil
from bond_lab.portfolio import Portfoy, Pozisyon
from bond_lab.risk import modifiye_durasyon


@pytest.fixture
def ornek_portfoy() -> Portfoy:
    """2Y, 5Y ve 10Y tahvillerden oluşan örnek portföy."""
    p = Portfoy(isim="Test")
    p.ekle(Pozisyon(Tahvil(100, 0.10, 2, 1, "2Y"), adet=100, ytm=0.11))
    p.ekle(Pozisyon(Tahvil(100, 0.12, 5, 2, "5Y"), adet=50, ytm=0.12))
    p.ekle(Pozisyon(Tahvil(100, 0.0, 10, 1, "10Y sıfır"), adet=200, ytm=0.13))
    return p


def test_toplam_deger_pozisyon_toplamina_esit(ornek_portfoy: Portfoy):
    """Portföy değeri, pozisyon piyasa değerlerinin toplamı olmalı."""
    beklenen = sum(p.piyasa_degeri for p in ornek_portfoy.pozisyonlar)
    assert ornek_portfoy.toplam_deger == pytest.approx(beklenen)


def test_agirliklar_toplami_bir(ornek_portfoy: Portfoy):
    """Piyasa değeri ağırlıklarının toplamı 1 olmalı."""
    assert sum(ornek_portfoy.agirliklar()) == pytest.approx(1.0)


def test_tek_pozisyonlu_portfoy_durasyonu_tahvile_esit():
    """Tek pozisyonlu portföyün durasyonu tahvilin durasyonuna eşit olmalı."""
    tahvil = Tahvil(100, 0.10, 5, 1)
    p = Portfoy()
    p.ekle(Pozisyon(tahvil, adet=10, ytm=0.12))
    assert p.portfoy_modifiye_durasyon() == pytest.approx(modifiye_durasyon(tahvil, 0.12))


def test_portfoy_durasyonu_bilesenler_arasinda(ornek_portfoy: Portfoy):
    """Ağırlıklı durasyon, en küçük ve en büyük pozisyon durasyonu arasında olmalı."""
    durasyonlar = [modifiye_durasyon(p.tahvil, p.ytm) for p in ornek_portfoy.pozisyonlar]
    d = ornek_portfoy.portfoy_modifiye_durasyon()
    assert min(durasyonlar) < d < max(durasyonlar)


def test_nakit_akisi_takvimi_toplami(ornek_portfoy: Portfoy):
    """Takvimdeki akış toplamı, pozisyon akışlarının adetli toplamına eşit olmalı."""
    takvim_toplam = sum(cf for _, cf in ornek_portfoy.nakit_akisi_takvimi())
    beklenen = sum(
        p.adet * sum(cf for _, cf in p.tahvil.nakit_akislari()) for p in ornek_portfoy.pozisyonlar
    )
    assert takvim_toplam == pytest.approx(beklenen)


def test_nakit_akisi_takvimi_sirali_ve_birlesik():
    """Aynı zamana düşen akışlar toplanmalı, takvim zamana göre sıralı olmalı."""
    p = Portfoy()
    p.ekle(Pozisyon(Tahvil(100, 0.10, 2, 1, "A"), adet=1, ytm=0.10))
    p.ekle(Pozisyon(Tahvil(100, 0.20, 2, 1, "B"), adet=1, ytm=0.10))
    takvim = p.nakit_akisi_takvimi()
    zamanlar = [t for t, _ in takvim]
    assert zamanlar == sorted(zamanlar)
    assert len(takvim) == 2  # t=1 ve t=2 (akışlar birleşti)
    assert takvim[0][1] == pytest.approx(10.0 + 20.0)


def test_senaryo_degeri_sifir_kaymada_esit(ornek_portfoy: Portfoy):
    """Sıfır kayma senaryosunda değer, mevcut toplam değere eşit olmalı."""
    assert ornek_portfoy.senaryo_degeri(lambda v: 0.0) == pytest.approx(ornek_portfoy.toplam_deger)


def test_gecersiz_pozisyon_adedi():
    """Pozitif olmayan adet ValueError üretmeli."""
    with pytest.raises(ValueError):
        Pozisyon(Tahvil(100, 0.10, 5, 1), adet=0, ytm=0.10)
