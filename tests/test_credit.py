"""credit ve inflation modülleri testleri: Z-spread, rating, Fisher."""

import pytest

from bond_lab.bond import Tahvil
from bond_lab.credit import (
    RATING_SPREAD_BP,
    rating_ile_fiyat,
    rating_spreadi,
    spread_duyarliligi,
    spreadli_fiyat,
    z_spread_bul,
)
from bond_lab.inflation import (
    EndeksliTahvil,
    basit_degerleme,
    endeks_orani,
    fisher_nominal,
    fisher_reel,
)
from bond_lab.pricing import spot_egriden_fiyat
from bond_lab.yield_curve import GetiriEgrisi


@pytest.fixture
def egri() -> GetiriEgrisi:
    return GetiriEgrisi([1, 2, 5, 10], [0.30, 0.28, 0.25, 0.23])


@pytest.fixture
def tahvil() -> Tahvil:
    return Tahvil(nominal=100, kupon_orani=0.26, vade_yil=5, frekans=1, isim="Test 5Y")


class TestSpread:
    def test_sifir_spread_risksiz_fiyata_esit(self, tahvil, egri):
        assert spreadli_fiyat(tahvil, egri, 0.0) == pytest.approx(spot_egriden_fiyat(tahvil, egri))

    def test_spread_arttikca_fiyat_duser(self, tahvil, egri):
        f0 = spreadli_fiyat(tahvil, egri, 0.0)
        f150 = spreadli_fiyat(tahvil, egri, 0.015)
        f300 = spreadli_fiyat(tahvil, egri, 0.030)
        assert f0 > f150 > f300

    def test_z_spread_gidis_donus(self, tahvil, egri):
        # Bilinen spread ile fiyatla, fiyattan spread'i geri çöz.
        gercek_spread = 0.0185
        kirli = spreadli_fiyat(tahvil, egri, gercek_spread)
        cozulen = z_spread_bul(tahvil, egri, kirli, temiz=False)
        assert cozulen == pytest.approx(gercek_spread, abs=1e-10)

    def test_z_spread_risksiz_fiyatta_sifir(self, tahvil, egri):
        kirli = spot_egriden_fiyat(tahvil, egri)
        assert z_spread_bul(tahvil, egri, kirli, temiz=False) == pytest.approx(0.0, abs=1e-10)

    def test_z_spread_gecersiz_fiyat_hata(self, tahvil, egri):
        with pytest.raises(ValueError):
            z_spread_bul(tahvil, egri, -5.0, temiz=False)

    def test_rating_tablosu_monoton(self):
        # Not düştükçe spread artmalı.
        sira = ["AAA", "AA", "A", "BBB", "BB", "B"]
        spreadler = [RATING_SPREAD_BP[r] for r in sira]
        assert spreadler == sorted(spreadler)

    def test_rating_ile_fiyat_dusuk_nottan_ucuz(self, tahvil, egri):
        assert rating_ile_fiyat(tahvil, egri, "AAA") > rating_ile_fiyat(tahvil, egri, "B")

    def test_rating_kucuk_harf_kabul(self):
        assert rating_spreadi("bbb") == pytest.approx(0.015)

    def test_bilinmeyen_rating_hata(self):
        with pytest.raises(ValueError):
            rating_spreadi("CCC")

    def test_spread_dv01_pozitif_ve_kucuk(self, tahvil, egri):
        duyarlilik = spread_duyarliligi(tahvil, egri, 0.015)
        assert 0.0 < duyarlilik < 1.0  # 1bp etkisi 100 nominalde küçük olmalı


class TestFisher:
    def test_fisher_tam_bicim(self):
        # (1.03)(1.40) - 1 = 0.442
        assert fisher_nominal(0.03, 0.40) == pytest.approx(0.442)

    def test_fisher_gidis_donus(self):
        nominal = fisher_nominal(0.025, 0.35)
        assert fisher_reel(nominal, 0.35) == pytest.approx(0.025, abs=1e-12)

    def test_fisher_yaklasik_bicim(self):
        assert fisher_nominal(0.03, 0.05, tam=False) == pytest.approx(0.08)
        assert fisher_reel(0.08, 0.05, tam=False) == pytest.approx(0.03)

    def test_dusuk_enflasyonda_yaklasik_tam_yakin(self):
        tam = fisher_nominal(0.02, 0.03)
        yaklasik = fisher_nominal(0.02, 0.03, tam=False)
        assert tam == pytest.approx(yaklasik, abs=0.001)


class TestEndeksliTahvil:
    def test_endeks_orani(self):
        assert endeks_orani(2172.0, 1810.0) == pytest.approx(1.2)

    def test_nominal_fiyat_endeksle_olceklenir(self):
        t1 = EndeksliTahvil(reel_kupon_orani=0.03, vade_yil=5, endeks_orani=1.0)
        t2 = EndeksliTahvil(reel_kupon_orani=0.03, vade_yil=5, endeks_orani=1.5)
        r = 0.025
        assert t2.nominal_fiyat(r) == pytest.approx(1.5 * t1.nominal_fiyat(r))

    def test_reel_fiyat_par(self):
        # Reel kupon = reel getiri → reel fiyat ≈ par.
        t = EndeksliTahvil(reel_kupon_orani=0.03, vade_yil=5, frekans=1)
        assert t.reel_fiyat(0.03) == pytest.approx(100.0, abs=1e-8)

    def test_taban_koruma_deflasyonda(self):
        # Endeks 1'in altında ve enflasyon beklentisi negatifse vade
        # anaparası reel nominalin altına inmemeli.
        t = EndeksliTahvil(
            reel_kupon_orani=0.0, vade_yil=3, frekans=1, endeks_orani=0.95, taban_koruma=True
        )
        akislar = t.nakit_akislari_nominal(beklenen_enflasyon=-0.02)
        son_zaman, son_tutar = akislar[-1]
        assert son_zaman == pytest.approx(3.0)
        assert son_tutar >= 100.0 - 1e-9

    def test_basit_degerleme_alanlari(self):
        t = EndeksliTahvil(reel_kupon_orani=0.03, vade_yil=5, endeks_orani=1.2)
        sonuc = basit_degerleme(t, reel_getiri=0.025, beklenen_enflasyon=0.30)
        assert sonuc["nominal_fiyat"] == pytest.approx(sonuc["reel_fiyat"] * 1.2)
        assert sonuc["nominal_esdeger_getiri"] == pytest.approx(fisher_nominal(0.025, 0.30))
        assert sonuc["duzeltilmis_anapara"] == pytest.approx(120.0)

    def test_gecersiz_endeks_hata(self):
        with pytest.raises(ValueError):
            EndeksliTahvil(endeks_orani=0.0)
