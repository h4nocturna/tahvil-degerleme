"""Tahvil sınıfı ve nakit akışı üretimi testleri."""

from datetime import date

import pytest

from bond_lab.bond import Tahvil


def test_kuponlu_nakit_akisi_sayisi_ve_tutarlari():
    """5 yıllık, 6 aylık kuponlu tahvilde 10 akış olmalı; son akış kupon+anapara."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.12, vade_yil=5, frekans=2)
    akislar = tahvil.nakit_akislari()
    assert len(akislar) == 10
    assert akislar[0] == pytest.approx((0.5, 6.0))
    assert akislar[-1] == pytest.approx((5.0, 106.0))
    # ara kuponların hepsi 6 = 100 * 0.12 / 2
    assert all(cf == pytest.approx(6.0) for _, cf in akislar[:-1])


def test_sifir_kuponlu_tek_akis():
    """Sıfır kuponlu tahvilde tek akış vardır: vadede nominal."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.0, vade_yil=7, frekans=1)
    assert tahvil.sifir_kuponlu
    assert tahvil.nakit_akislari() == [(7.0, 100.0)]


def test_kesirli_vade_akis_zamanlari():
    """Vade 4.75 yıl, yıllık kupon: akışlar 0.75, 1.75, ..., 4.75'te olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=4.75, frekans=1)
    zamanlar = [t for t, _ in tahvil.nakit_akislari()]
    assert zamanlar == pytest.approx([0.75, 1.75, 2.75, 3.75, 4.75])


def test_islemis_faiz_kupon_gununde_sifir():
    """Vade dönem uzunluğunun tam katıysa işlemiş faiz 0 olmalı."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
    assert tahvil.islemis_faiz() == pytest.approx(0.0)


def test_islemis_faiz_kesirli_vade():
    """Vade 4.75 yıl → dönemin %25'i geçmiş → işlemiş faiz = 0.25 × kupon."""
    tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=4.75, frekans=1)
    assert tahvil.islemis_donem_orani == pytest.approx(0.25)
    assert tahvil.islemis_faiz() == pytest.approx(0.25 * 10.0)


def test_gecersiz_girdiler_hata_verir():
    """Negatif/uygunsuz parametreler ValueError üretmeli."""
    with pytest.raises(ValueError):
        Tahvil(nominal=-100, kupon_orani=0.1, vade_yil=5)
    with pytest.raises(ValueError):
        Tahvil(nominal=100, kupon_orani=-0.1, vade_yil=5)
    with pytest.raises(ValueError):
        Tahvil(nominal=100, kupon_orani=0.1, vade_yil=0)
    with pytest.raises(ValueError):
        Tahvil(nominal=100, kupon_orani=0.1, vade_yil=5, frekans=3)


def test_tarihlerden_kurucu():
    """Tarihlerden kurulan tahvilin vadesi ACT/365 ile hesaplanmalı."""
    tahvil = Tahvil.tarihlerden(
        nominal=100,
        kupon_orani=0.10,
        valor_tarihi=date(2026, 1, 1),
        vade_tarihi=date(2031, 1, 1),
        frekans=1,
    )
    # 2026-2031 arasında 1826 gün (2028 artık yıl) → 1826/365 ≈ 5.0027 yıl
    assert tahvil.vade_yil == pytest.approx(1826 / 365)
    with pytest.raises(ValueError):
        Tahvil.tarihlerden(100, 0.1, date(2026, 1, 1), date(2026, 1, 1))
