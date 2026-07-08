"""market_data ve report modülleri testleri (internet GEREKTİRMEZ).

FRED çağrısı gerçek ağa çıkmadan, requests.get mock'lanarak test edilir.
"""

from unittest import mock

import pandas as pd
import pytest

from bond_lab.bond import Tahvil
from bond_lab.market_data import (
    FRED_SERILERI,
    _fred_csv_ayristir,
    dibs_ornek_egrisi,
    dibs_ornek_seti,
    egriyi_csvden_yukle,
    fred_hazine_egrisi,
    kotasyonlardan_enstrumanlar,
    ornek_csvleri_yaz,
    tahvilleri_csvden_yukle,
    ust_egrisi_getir,
    ust_ornek_egrisi,
)
from bond_lab.pricing import temiz_fiyat, ytm_bul
from bond_lab.report import excele_yaz, fiyatlama_tablosu, rapor_uret
from bond_lab.yield_curve import GetiriEgrisi

SAHTE_FRED_CSV = """observation_date,DGS3MO,DGS6MO,DGS1,DGS2,DGS5,DGS10,DGS30
2026-06-29,4.30,4.25,4.10,3.95,3.90,4.05,4.45
2026-06-30,4.32,.,4.12,3.93,3.88,4.07,4.46
"""


class TestGomuluVeri:
    def test_dibs_seti_fiyat_getiri_tutarli(self):
        # Gömülü fiyat, gömülü getiriden türetilmiş olmalı (gidiş-dönüş).
        for k in dibs_ornek_seti():
            geri_ytm = ytm_bul(k.tahvil(), k.temiz_fiyat, temiz=True)
            assert geri_ytm == pytest.approx(k.ytm, abs=5e-4)

    def test_dibs_egrisi_ters_egri(self):
        # Temsili TL seti: kısa uç getirisi uzun uçtan yüksek (ters eğri).
        egri = dibs_ornek_egrisi()
        assert egri.oranlar[0] > egri.oranlar[-1]
        assert "temsili" in egri.kaynak.lower()

    def test_ust_egrisi_spot_egriye_cevrilir(self):
        spot = ust_ornek_egrisi().spot_egri()
        assert isinstance(spot, GetiriEgrisi)
        assert 0.0 < spot.spot_oran(10.0) < 0.10

    def test_bootstrap_enstrumanlari(self):
        enstrumanlar = kotasyonlardan_enstrumanlar(dibs_ornek_seti())
        egri = GetiriEgrisi.bootstrap(enstrumanlar, temiz=True)
        assert len(egri.vadeler) == len(enstrumanlar)


class TestFred:
    def test_csv_ayristirici_eksik_gozlem_atlar(self):
        gozlemler = _fred_csv_ayristir(SAHTE_FRED_CSV)
        # DGS6MO'nun 30 Haziran değeri '.' → son geçerli gözlem 29 Haziran.
        assert gozlemler["DGS6MO"] == ("2026-06-29", pytest.approx(0.0425))
        assert gozlemler["DGS10"] == ("2026-06-30", pytest.approx(0.0407))

    def test_fred_mock_basarili(self):
        yanit = mock.Mock()
        yanit.text = SAHTE_FRED_CSV
        yanit.raise_for_status = mock.Mock()
        with mock.patch("requests.get", return_value=yanit) as m:
            egri = fred_hazine_egrisi()
        assert m.called
        assert egri is not None
        assert egri.kaynak == "FRED (canlı)"
        assert len(egri.vadeler) == len(FRED_SERILERI)
        assert egri.tarih == "2026-06-30"

    def test_fred_ag_hatasi_none_doner(self):
        with mock.patch("requests.get", side_effect=OSError("ağ yok")):
            assert fred_hazine_egrisi() is None

    def test_ust_egrisi_getir_gomulu_yedek(self):
        # Canlı istek başarısızsa sessizce temsili veriye düşmeli.
        with mock.patch("requests.get", side_effect=OSError("ağ yok")):
            egri = ust_egrisi_getir(canli_dene=True)
        assert "temsili" in egri.kaynak.lower()

    def test_ust_egrisi_getir_canli_kapali(self):
        egri = ust_egrisi_getir(canli_dene=False)
        assert "temsili" in egri.kaynak.lower()


class TestCsvIo:
    def test_ornek_csvler_yazilir_ve_yuklenir(self, tmp_path):
        yollar = ornek_csvleri_yaz(tmp_path)
        assert all(y.exists() and y.stat().st_size > 0 for y in yollar)

        kotasyonlar = tahvilleri_csvden_yukle(tmp_path / "dibs_ornek.csv")
        assert len(kotasyonlar) == len(dibs_ornek_seti())

        egri = egriyi_csvden_yukle(tmp_path / "ust_egri_ornek.csv")
        beklenen = ust_ornek_egrisi()
        assert egri.vadeler == beklenen.vadeler
        assert egri.oranlar == pytest.approx(beklenen.oranlar)

    def test_fiyattan_ytm_turetilir(self, tmp_path):
        # ytm sütunu boşsa temiz fiyattan çözülmeli.
        yol = tmp_path / "tek.csv"
        t = Tahvil(nominal=100, kupon_orani=0.20, vade_yil=3, frekans=1)
        fiyat = temiz_fiyat(t, 0.25)
        yol.write_text(
            "isim,vade_yil,kupon_orani,frekans,ytm,temiz_fiyat\n" f"Deneme,3,0.20,1,,{fiyat:.6f}\n",
            encoding="utf-8",
        )
        kotasyonlar = tahvilleri_csvden_yukle(yol)
        assert kotasyonlar[0].ytm == pytest.approx(0.25, abs=1e-6)

    def test_bozuk_csv_hata(self, tmp_path):
        yol = tmp_path / "bozuk.csv"
        yol.write_text("isim,vade_yil,kupon_orani\nX,abc,0.1\n", encoding="utf-8")
        with pytest.raises(ValueError):
            tahvilleri_csvden_yukle(yol)

    def test_bos_csv_hata(self, tmp_path):
        yol = tmp_path / "bos.csv"
        yol.write_text("vade_yil,oran\n", encoding="utf-8")
        with pytest.raises(ValueError):
            egriyi_csvden_yukle(yol)


class TestRapor:
    def test_fiyatlama_tablosu_turkce_basliklar(self):
        t = Tahvil(nominal=100, kupon_orani=0.25, vade_yil=2, frekans=1, isim="2Y")
        df = fiyatlama_tablosu([t], [0.30])
        for kolon in ("Tahvil", "Temiz Fiyat", "Macaulay (yıl)", "Konveksite"):
            assert kolon in df.columns

    def test_excel_ve_csv_uretimi(self, tmp_path):
        t = Tahvil(nominal=100, kupon_orani=0.25, vade_yil=2, frekans=1, isim="2Y")
        df = fiyatlama_tablosu([t], [0.30])
        sonuc = rapor_uret(fiyatlama=df, dosya_adi="test_rapor.xlsx", cikti_klasoru=tmp_path)
        excel = sonuc["excel"][0]
        assert excel.exists() and excel.stat().st_size > 0
        assert sonuc["csv"] and all(y.exists() for y in sonuc["csv"])
        # Excel gerçekten okunabilir ve Özet sayfası var mı?
        sayfalar = pd.read_excel(excel, sheet_name=None)
        assert "Özet" in sayfalar and "Fiyatlama" in sayfalar

    def test_uzun_sayfa_adi_kirpilir(self, tmp_path):
        df = pd.DataFrame({"a": [1]})
        cok_uzun = "Çok Uzun Bir Sayfa Adı " * 3
        yol = excele_yaz({cok_uzun: df}, dosya_adi="uzun.xlsx", cikti_klasoru=tmp_path)
        sayfalar = pd.read_excel(yol, sheet_name=None)
        assert all(len(ad) <= 31 for ad in sayfalar)

    def test_bos_rapor_hata(self, tmp_path):
        with pytest.raises(ValueError):
            rapor_uret(cikti_klasoru=tmp_path)
