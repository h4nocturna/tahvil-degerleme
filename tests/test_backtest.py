"""backtest modülü testleri: patikalar, Vasicek, strateji karşılaştırması."""

import numpy as np
import pytest

from bond_lab.backtest import (
    backtest_grafigi,
    deterministik_patikalar,
    portfoy_backtest,
    stratejileri_backtest_et,
    vasicek_patikalari,
    yillik_getiri,
)
from bond_lab.strategies import bullet_portfoy, merdiven_portfoy
from bond_lab.yield_curve import GetiriEgrisi


@pytest.fixture
def egri() -> GetiriEgrisi:
    return GetiriEgrisi([1, 2, 3, 5, 7, 10], [0.36, 0.33, 0.30, 0.27, 0.25, 0.23])


class TestPatikalar:
    def test_deterministik_bicim_ve_baslangic(self):
        patikalar = deterministik_patikalar(3.0, 12)
        assert len(patikalar) == 5
        for kaymalar in patikalar.values():
            assert len(kaymalar) == 13
            assert kaymalar[0] == pytest.approx(0.0)

    def test_kademeli_artis_ufukta_hedefe_ulasir(self):
        patikalar = deterministik_patikalar(3.0, 12, toplam_bp=300.0)
        artis = patikalar["Kademeli artış (+300bp)"]
        assert artis[-1] == pytest.approx(0.03)

    def test_gecersiz_adim_hata(self):
        with pytest.raises(ValueError):
            deterministik_patikalar(3.0, 0)

    def test_vasicek_seed_tekrarlanabilir(self):
        a = vasicek_patikalari(0.30, 3.0, 12, patika_sayisi=50, seed=7)
        b = vasicek_patikalari(0.30, 3.0, 12, patika_sayisi=50, seed=7)
        assert np.array_equal(a, b)

    def test_vasicek_farkli_seed_farkli(self):
        a = vasicek_patikalari(0.30, 3.0, 12, patika_sayisi=50, seed=7)
        b = vasicek_patikalari(0.30, 3.0, 12, patika_sayisi=50, seed=8)
        assert not np.array_equal(a, b)

    def test_vasicek_boyut_ve_baslangic(self):
        r = vasicek_patikalari(0.25, 2.0, 8, patika_sayisi=30, seed=1)
        assert r.shape == (30, 9)
        assert np.allclose(r[:, 0], 0.25)

    def test_vasicek_ortalamaya_donus(self):
        # Yüksek başlangıç, düşük hedef: ortalama patika hedefe yaklaşmalı.
        r = vasicek_patikalari(0.40, 10.0, 40, patika_sayisi=500, a=0.5, b=0.20, sigma=0.01, seed=3)
        son_ortalama = float(np.mean(r[:, -1]))
        assert abs(son_ortalama - 0.20) < abs(0.40 - 0.20) / 2


class TestPortfoyBacktest:
    def test_sabit_patikada_getiri_ytm_yakini(self, egri):
        # Faiz hiç değişmezse 1 yıllık bullet'ın getirisi kabaca YTM olmalı.
        p = bullet_portfoy(100_000, 1.0, egri, frekans=1)
        zamanlar = np.linspace(0.0, 1.0, 5)
        kaymalar = np.zeros(5)
        getiri = portfoy_backtest(p, kaymalar, zamanlar, kisa_oran0=egri.spot_oran(1.0))
        assert getiri == pytest.approx(egri.spot_oran(1.0), abs=0.02)

    def test_faiz_artisinda_uzun_bullet_merdivenden_kotu(self, egri):
        # İşaret kontrolü: kademeli faiz artışında uzun durasyonlu bullet,
        # kısa vadelere yayılmış merdivenden KÖTÜ performans göstermeli.
        tutar = 1_000_000.0
        merdiven = merdiven_portfoy(tutar, list(range(1, 11)), egri)
        bullet = bullet_portfoy(tutar, 10.0, egri)
        adim = 12
        zamanlar = np.linspace(0.0, 3.0, adim + 1)
        artis = np.linspace(0.0, 0.03, adim + 1)  # +300bp kademeli
        kisa0 = egri.spot_oran(1.0)
        g_merdiven = portfoy_backtest(merdiven, artis, zamanlar, kisa0)
        g_bullet = portfoy_backtest(bullet, artis, zamanlar, kisa0)
        assert g_bullet < g_merdiven

    def test_faiz_dususunde_uzun_bullet_kazanir(self):
        # DÜZ eğri kullanılır ki taşıma (carry) tüm stratejilerde eşit olsun
        # ve yalnızca durasyon etkisi ölçülsün: düşüşte uzun bullet kazanmalı.
        duz_egri = GetiriEgrisi([1, 10], [0.30, 0.30])
        tutar = 1_000_000.0
        merdiven = merdiven_portfoy(tutar, list(range(1, 11)), duz_egri)
        bullet = bullet_portfoy(tutar, 10.0, duz_egri)
        adim = 12
        zamanlar = np.linspace(0.0, 3.0, adim + 1)
        dusus = np.linspace(0.0, -0.03, adim + 1)
        kisa0 = duz_egri.spot_oran(1.0)
        assert portfoy_backtest(bullet, dusus, zamanlar, kisa0) > portfoy_backtest(
            merdiven, dusus, zamanlar, kisa0
        )

    def test_uzunluk_uyusmazligi_hata(self, egri):
        p = bullet_portfoy(1000, 5.0, egri)
        with pytest.raises(ValueError):
            portfoy_backtest(p, [0.0, 0.01], [0.0, 1.0, 2.0], 0.3)

    def test_yillik_getiri_donusumu(self):
        # 2 yılda %21 toplam → yıllık %10.
        assert yillik_getiri(0.21, 2.0) == pytest.approx(0.10, abs=1e-12)


class TestKarsilastirmaMotoru:
    def test_tablolar_ve_grafik(self, egri, tmp_path):
        sonuc = stratejileri_backtest_et(egri, ufuk_yil=2.0, patika_sayisi=40, seed=11)
        assert set(sonuc.deterministik.columns) == {"Merdiven", "Barbell", "Bullet"}
        assert len(sonuc.deterministik.index) == 5
        assert list(sonuc.stokastik_ozet.columns) == ["Ortalama %", "Std %", "Min %", "Maks %"]
        # Min <= Ortalama <= Maks tutarlılığı.
        for strateji in sonuc.stokastik_ozet.index:
            satir = sonuc.stokastik_ozet.loc[strateji]
            assert satir["Min %"] <= satir["Ortalama %"] <= satir["Maks %"]
        yol = backtest_grafigi(sonuc, cikti_klasoru=tmp_path)
        assert yol.exists() and yol.stat().st_size > 0

    def test_deterministik_isaretler(self, egri):
        # Ani −200bp şokunda bullet, ani +200bp şokundan daha iyi olmalı.
        sonuc = stratejileri_backtest_et(egri, ufuk_yil=2.0, patika_sayisi=10, seed=5)
        df = sonuc.deterministik
        assert df.loc["Ani şok −200bp", "Bullet"] > df.loc["Ani şok +200bp", "Bullet"]
