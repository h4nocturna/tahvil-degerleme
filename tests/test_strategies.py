"""Strateji motoru testleri: kurucular, senaryolar, immünizasyon, öneri."""

import pytest

from bond_lab.strategies import (
    GECERLI_BEKLENTILER,
    GECERLI_TOLERANSLAR,
    StratejiOnerisi,
    barbell_portfoy,
    bullet_portfoy,
    immunizasyon_portfoy,
    merdiven_portfoy,
    senaryo_analizi,
    standart_senaryolar,
    strateji_oner,
)
from bond_lab.yield_curve import GetiriEgrisi


@pytest.fixture
def egri() -> GetiriEgrisi:
    """Azalan (ters) örnek getiri eğrisi."""
    return GetiriEgrisi([1, 2, 3, 5, 7, 10], [0.36, 0.33, 0.30, 0.27, 0.25, 0.23])


def test_merdiven_esit_agirlik(egri: GetiriEgrisi):
    """Merdivende para ağırlıkları eşit ve toplamı 1 olmalı."""
    p = merdiven_portfoy(1_000_000, [1, 2, 3, 4, 5], egri)
    agirliklar = p.agirliklar()
    assert len(agirliklar) == 5
    assert sum(agirliklar) == pytest.approx(1.0)
    assert all(w == pytest.approx(0.2, abs=1e-9) for w in agirliklar)
    assert p.toplam_deger == pytest.approx(1_000_000)


def test_bullet_tek_pozisyon(egri: GetiriEgrisi):
    """Bullet tek pozisyondan oluşmalı; ağırlığı 1, değeri yatırılan tutar."""
    p = bullet_portfoy(500_000, 5, egri)
    assert len(p.pozisyonlar) == 1
    assert p.agirliklar() == pytest.approx([1.0])
    assert p.toplam_deger == pytest.approx(500_000)


def test_barbell_iki_uc_ve_agirlik(egri: GetiriEgrisi):
    """Barbell iki pozisyon içermeli; ağırlıklar istenen bölüşüme eşit olmalı."""
    p = barbell_portfoy(1_000_000, 2, 10, egri, kisa_agirlik=0.4)
    agirliklar = p.agirliklar()
    assert len(p.pozisyonlar) == 2
    assert sum(agirliklar) == pytest.approx(1.0)
    assert agirliklar[0] == pytest.approx(0.4, abs=1e-9)
    assert agirliklar[1] == pytest.approx(0.6, abs=1e-9)


def test_barbell_gecersiz_girdiler(egri: GetiriEgrisi):
    """Ters vade sırası ve uç ağırlıklar hata vermeli."""
    with pytest.raises(ValueError):
        barbell_portfoy(1000, 10, 2, egri)
    with pytest.raises(ValueError):
        barbell_portfoy(1000, 2, 10, egri, kisa_agirlik=1.0)


def test_merdiven_az_vade_hata(egri: GetiriEgrisi):
    """Tek vadeli merdiven anlamsızdır; hata vermeli."""
    with pytest.raises(ValueError):
        merdiven_portfoy(1000, [5], egri)


def test_senaryo_isaretleri(egri: GetiriEgrisi):
    """Faiz artışında portföy değeri düşmeli, düşüşünde artmalı."""
    p = merdiven_portfoy(1_000_000, list(range(1, 11)), egri)
    sonuc = senaryo_analizi(p)
    assert sonuc["Paralel +100bp"]["degisim"] < 0
    assert sonuc["Paralel -100bp"]["degisim"] > 0
    assert sonuc["Paralel +200bp"]["degisim"] < sonuc["Paralel +100bp"]["degisim"]


def test_senaryo_uzun_durasyon_daha_duyarli(egri: GetiriEgrisi):
    """Uzun vadeli bullet, kısa vadeliden faiz artışında daha çok kaybetmeli."""
    kisa = bullet_portfoy(1_000_000, 2, egri)
    uzun = bullet_portfoy(1_000_000, 10, egri)
    s_kisa = senaryo_analizi(kisa)["Paralel +100bp"]["degisim_yuzde"]
    s_uzun = senaryo_analizi(uzun)["Paralel +100bp"]["degisim_yuzde"]
    assert s_uzun < s_kisa < 0


def test_standart_senaryolar_kapsami_ve_degerleri():
    """Standart senaryolar paralel ±50/±100/±200bp ve eğim senaryolarını içermeli."""
    senaryolar = standart_senaryolar()
    assert len(senaryolar) == 8
    assert senaryolar["Paralel +100bp"](3.0) == pytest.approx(0.01)
    assert senaryolar["Paralel -200bp"](7.0) == pytest.approx(-0.02)
    dik = senaryolar["Dikleşme (kısa−/uzun+)"]
    assert dik(0.0) == pytest.approx(-0.005)
    assert dik(10.0) == pytest.approx(+0.005)
    assert dik(20.0) == pytest.approx(+0.005)  # pivotun ötesinde sabit
    yat = senaryolar["Yataylaşma (kısa+/uzun−)"]
    assert yat(0.0) == pytest.approx(+0.005)
    assert yat(10.0) == pytest.approx(-0.005)


def test_immunizasyon_durasyon_eslesmesi(egri: GetiriEgrisi):
    """İmmünizasyon portföyünün Macaulay durasyonu hedef ufka eşit olmalı."""
    hedef = 4.0
    p = immunizasyon_portfoy(1_000_000, hedef, 2, 10, egri)
    assert p.portfoy_macaulay_durasyon() == pytest.approx(hedef, abs=1e-9)
    assert sum(p.agirliklar()) == pytest.approx(1.0)
    assert p.toplam_deger == pytest.approx(1_000_000)


def test_immunizasyon_hedef_aralik_disi_hata(egri: GetiriEgrisi):
    """Hedef ufuk iki tahvilin durasyon aralığı dışındaysa hata vermeli."""
    with pytest.raises(ValueError):
        immunizasyon_portfoy(1_000_000, 15.0, 2, 10, egri)
    with pytest.raises(ValueError):
        immunizasyon_portfoy(1_000_000, 0.5, 2, 10, egri)


@pytest.mark.parametrize("beklenti", GECERLI_BEKLENTILER)
@pytest.mark.parametrize("tolerans", GECERLI_TOLERANSLAR)
def test_strateji_oner_tum_profiller(beklenti: str, tolerans: str):
    """Tüm 9 profil kombinasyonu geçerli ve gerekçeli öneri üretmeli."""
    oneri = strateji_oner(beklenti, 5.0, tolerans)
    assert isinstance(oneri, StratejiOnerisi)
    assert oneri.strateji in ("merdiven", "barbell", "bullet", "immünizasyon")
    assert oneri.hedef_durasyon > 0
    assert len(oneri.gerekce) > 50  # dolu, açıklayıcı Türkçe metin


def test_strateji_oner_yon_mantigi():
    """Yükseliş beklentisinde durasyon, düşüş beklentisindekinden kısa olmalı."""
    ufuk = 5.0
    kisa = strateji_oner("yukselecek", ufuk, "orta").hedef_durasyon
    uzun = strateji_oner("dusecek", ufuk, "yuksek").hedef_durasyon
    assert kisa < ufuk <= uzun


def test_strateji_oner_gecersiz_girdiler():
    """Geçersiz beklenti/tolerans/ufuk ValueError üretmeli."""
    with pytest.raises(ValueError):
        strateji_oner("bilinmiyor", 5.0, "orta")
    with pytest.raises(ValueError):
        strateji_oner("sabit", 5.0, "cok_yuksek")
    with pytest.raises(ValueError):
        strateji_oner("sabit", -1.0, "orta")
