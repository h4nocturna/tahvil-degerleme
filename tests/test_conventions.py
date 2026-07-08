"""conventions modülü testleri: gün sayım, valör kaydırma, işlemiş faiz."""

from datetime import date

import pytest

from bond_lab.conventions import (
    islemis_faiz_tarihli,
    kupon_tarihleri,
    onceki_ve_sonraki_kupon,
    sonraki_is_gunu,
    valor_tarihi,
    yil_kesri,
)


class TestYilKesri:
    def test_act_365f_bilinen_ornek(self):
        # 2026-01-15 → 2026-07-15 = 181 gün
        assert yil_kesri(date(2026, 1, 15), date(2026, 7, 15), "ACT/365F") == pytest.approx(
            181 / 365
        )

    def test_act_360_bilinen_ornek(self):
        assert yil_kesri(date(2026, 1, 15), date(2026, 7, 15), "ACT/360") == pytest.approx(
            181 / 360
        )

    def test_30_360_tam_alti_ay(self):
        # 30/360'ta yarım yıl her zaman tam 0.5'tir.
        assert yil_kesri(date(2026, 1, 15), date(2026, 7, 15), "30/360") == pytest.approx(0.5)

    def test_30_360_ay_sonu_kurali(self):
        # Başlangıç 31'i → 30'a çekilir: 31 Oca → 28 Şub = 28 gün sayılır.
        assert yil_kesri(date(2026, 1, 31), date(2026, 2, 28), "30/360") == pytest.approx(28 / 360)

    def test_act_act_artik_yil(self):
        # 2028 artık yıl: tam yıl kesri 1.0 olmalı (366/366).
        assert yil_kesri(date(2028, 1, 1), date(2029, 1, 1), "ACT/ACT") == pytest.approx(1.0)

    def test_act_act_yil_gecisi(self):
        # 2027-07-01 → 2028-07-01: 184/365 + 182/366 (2028 artık).
        beklenen = 184 / 365 + 182 / 366
        assert yil_kesri(date(2027, 7, 1), date(2028, 7, 1), "ACT/ACT") == pytest.approx(beklenen)

    def test_tam_yil_tum_konvansiyonlar_yakin(self):
        b, s = date(2026, 3, 10), date(2027, 3, 10)
        for k in ("ACT/365F", "30/360", "ACT/ACT"):
            assert yil_kesri(b, s, k) == pytest.approx(1.0, abs=0.01)

    def test_gecersiz_konvansiyon_hata(self):
        with pytest.raises(ValueError):
            yil_kesri(date(2026, 1, 1), date(2026, 2, 1), "ACT/366")

    def test_ters_tarih_hata(self):
        with pytest.raises(ValueError):
            yil_kesri(date(2026, 2, 1), date(2026, 1, 1))


class TestValorTarihi:
    def test_hafta_ici_t2(self):
        # Çarşamba (2026-07-08) + T+2 = Cuma.
        assert valor_tarihi(date(2026, 7, 8), 2) == date(2026, 7, 10)

    def test_cuma_t2_hafta_sonu_atlar(self):
        # Cuma (2026-07-10) + T+2 → Pzt, Salı = 2026-07-14.
        assert valor_tarihi(date(2026, 7, 10), 2) == date(2026, 7, 14)

    def test_cumartesi_islem_ilk_is_gununden_baslar(self):
        # Cumartesi işlem → Pazartesi kabul, T+1 = Salı.
        assert valor_tarihi(date(2026, 7, 11), 1) == date(2026, 7, 14)

    def test_t0_ayni_gun(self):
        assert valor_tarihi(date(2026, 7, 8), 0) == date(2026, 7, 8)

    def test_negatif_takas_hata(self):
        with pytest.raises(ValueError):
            valor_tarihi(date(2026, 7, 8), -1)

    def test_sonraki_is_gunu_pazar(self):
        assert sonraki_is_gunu(date(2026, 7, 12)) == date(2026, 7, 13)


class TestKuponTakvimi:
    def test_yillik_kupon_tarihleri(self):
        tarihler = kupon_tarihleri(date(2029, 6, 15), 1, date(2026, 7, 8))
        assert tarihler == [date(2027, 6, 15), date(2028, 6, 15), date(2029, 6, 15)]

    def test_alti_aylik_kupon_sayisi(self):
        tarihler = kupon_tarihleri(date(2028, 1, 15), 2, date(2026, 7, 8))
        assert len(tarihler) == 4  # 2026-07-15*, 2027-01-15, 2027-07-15, 2028-01-15
        assert tarihler[-1] == date(2028, 1, 15)

    def test_onceki_sonraki_kupon_cevreler(self):
        onceki, sonraki = onceki_ve_sonraki_kupon(date(2029, 6, 15), 1, date(2026, 7, 8))
        assert onceki <= date(2026, 7, 8) < sonraki
        assert (onceki, sonraki) == (date(2026, 6, 15), date(2027, 6, 15))


class TestIslemisFaizTarihli:
    def test_kupon_gunu_sifir(self):
        # Valör tam önceki kupon günündeyse işlemiş faiz ~0 olmalı.
        faiz = islemis_faiz_tarihli(100, 0.10, 1, date(2029, 6, 15), date(2026, 6, 15))
        assert faiz == pytest.approx(0.0, abs=1e-9)

    def test_donem_ortasi_yariya_yakin(self):
        # Yıllık kuponda dönem ortası ≈ kuponun yarısı.
        faiz = islemis_faiz_tarihli(100, 0.10, 1, date(2029, 6, 15), date(2026, 12, 15), "ACT/ACT")
        assert faiz == pytest.approx(5.0, abs=0.15)

    def test_sifir_kupon_sifir_faiz(self):
        assert islemis_faiz_tarihli(100, 0.0, 1, date(2029, 6, 15), date(2026, 7, 8)) == 0.0

    def test_faiz_kupon_tutarini_asamaz(self):
        faiz = islemis_faiz_tarihli(100, 0.20, 2, date(2030, 3, 20), date(2026, 7, 8), "ACT/365F")
        assert 0.0 <= faiz <= 10.0  # 6 aylık kupon tutarı = 10
