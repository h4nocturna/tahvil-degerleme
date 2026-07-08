"""Tahvil değerleme ve strateji analizi — uçtan uca Türkçe demo/CLI.

Kullanım:
    python main.py                  # tam demo (varsayılan)
    python main.py demo             # tam demo
    python main.py fiyatla --kupon 0.10 --vade 5 --ytm 0.12
    python main.py oner --beklenti dusecek --ufuk 5 --risk orta
    python main.py backtest --ufuk 3            # strateji backtest'i
    python main.py rapor                        # Excel + CSV raporu üret
    python main.py web                          # Streamlit arayüzünü başlat

Demo; örnek tahvilleri fiyatlar, YTM/durasyon/konveksite hesaplar, örnek
piyasa verisinden spot eğri bootstrap eder, üç stratejiyi (merdiven/
barbell/bullet) kurar, faiz senaryosu analizini koşar, strateji önerisi
verir, backtest özeti ve Excel raporu üretir; grafikleri ``output/``
klasörüne PNG olarak kaydeder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:  # yalnızca tip denetimi için; çalışma zamanında import edilmez
    from bond_lab.backtest import BacktestKarsilastirma

from bond_lab import (
    GetiriEgrisi,
    Tahvil,
    barbell_portfoy,
    bullet_portfoy,
    cari_getiri,
    dv01,
    fiyat_degisim_karsilastir,
    immunizasyon_portfoy,
    kirli_fiyat,
    konveksite,
    macaulay_durasyon,
    merdiven_portfoy,
    modifiye_durasyon,
    nelson_siegel_uydur,
    senaryo_analizi,
    spot_egriden_fiyat,
    standart_senaryolar,
    strateji_oner,
    temiz_fiyat,
    ytm_bul,
)
from bond_lab.visualization import (
    fiyat_getiri_grafigi,
    getiri_egrisi_grafigi,
    nakit_akisi_grafigi,
    strateji_karsilastirma_grafigi,
)

CIKTI_KLASORU = Path(__file__).resolve().parent / "output"


def _konsolu_utf8_yap() -> None:
    """Windows konsolunda Türkçe karakter sorununu önler (cp1254/cp437)."""
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def baslik(metin: str) -> None:
    """Bölüm başlığı yazar."""
    print()
    print("=" * 78)
    print(f"  {metin}")
    print("=" * 78)


def tablo_yaz(df: pd.DataFrame, ondalik: int = 4) -> None:
    """DataFrame'i düzgün hizalı Türkçe tablo olarak yazar."""
    print(df.to_string(float_format=lambda x: f"{x:,.{ondalik}f}"))


# ----------------------------------------------------------------------
# Demo bölümleri
# ----------------------------------------------------------------------
def bolum_fiyatlama() -> list[Tahvil]:
    """Örnek tahvilleri tanımlar ve fiyatlama/YTM tablosunu yazar."""
    baslik("1) TAHVİL TANIMLARI VE FİYATLAMA")
    tahviller = [
        Tahvil(nominal=100, kupon_orani=0.10, vade_yil=2, frekans=1, isim="2Y %10 yıllık kupon"),
        Tahvil(nominal=100, kupon_orani=0.12, vade_yil=5, frekans=2, isim="5Y %12 6 aylık kupon"),
        Tahvil(nominal=100, kupon_orani=0.0, vade_yil=10, frekans=1, isim="10Y sıfır kuponlu"),
        Tahvil(
            nominal=100, kupon_orani=0.10, vade_yil=4.75, frekans=1, isim="4.75Y %10 (kesirli vade)"
        ),
    ]
    piyasa_ytm = [0.12, 0.11, 0.13, 0.12]

    satirlar = []
    for tahvil, ytm in zip(tahviller, piyasa_ytm, strict=True):
        kirli = kirli_fiyat(tahvil, ytm)
        temiz = temiz_fiyat(tahvil, ytm)
        geri_ytm = ytm_bul(tahvil, temiz, temiz=True)
        satirlar.append(
            {
                "Tahvil": tahvil.isim,
                "Piyasa YTM %": ytm * 100,
                "Kirli Fiyat": kirli,
                "İşlemiş Faiz": tahvil.islemis_faiz(),
                "Temiz Fiyat": temiz,
                "Cari Getiri %": cari_getiri(tahvil, temiz) * 100 if temiz > 0 else 0.0,
                "Fiyattan YTM %": geri_ytm * 100,
            }
        )
    tablo_yaz(pd.DataFrame(satirlar).set_index("Tahvil"))
    print("\nNot: 'Fiyattan YTM' sütunu, temiz fiyattan Newton-Raphson ile geri")
    print("çözülen getiridir; 'Piyasa YTM' ile birebir örtüşmesi gidiş-dönüş")
    print("tutarlılığını gösterir.")
    return tahviller


def bolum_risk(tahviller: list[Tahvil]) -> None:
    """Durasyon/konveksite tablosu ve tahmin-gerçek karşılaştırması."""
    baslik("2) FAİZ RİSKİ: DURASYON, KONVEKSİTE, DV01")
    ytm = 0.12
    satirlar = []
    for tahvil in tahviller:
        satirlar.append(
            {
                "Tahvil": tahvil.isim,
                "Macaulay (yıl)": macaulay_durasyon(tahvil, ytm),
                "Modifiye": modifiye_durasyon(tahvil, ytm),
                "DV01": dv01(tahvil, ytm),
                "Konveksite": konveksite(tahvil, ytm),
            }
        )
    tablo_yaz(pd.DataFrame(satirlar).set_index("Tahvil"))

    print(f"\n+200bp şoku için tahmin kalitesi (YTM %{ytm * 100:.0f} → %{(ytm + 0.02) * 100:.0f}):")
    satirlar = []
    for tahvil in tahviller:
        k = fiyat_degisim_karsilastir(tahvil, ytm, 0.02)
        satirlar.append(
            {
                "Tahvil": tahvil.isim,
                "Gerçek ΔF": k["gercek_degisim"],
                "Tahmin (durasyon)": k["tahmin_durasyon"],
                "Tahmin (dur+konv)": k["tahmin_durasyon_konveksite"],
                "Hata (durasyon)": k["mutlak_hata_durasyon"],
                "Hata (dur+konv)": k["mutlak_hata_durasyon_konveksite"],
            }
        )
    tablo_yaz(pd.DataFrame(satirlar).set_index("Tahvil"))
    print("\nKonveksite düzeltmesi eklenince tahmin hatasının belirgin azaldığına")
    print("dikkat edin; fiyat-getiri ilişkisi dışbükey olduğundan yalnız durasyon")
    print("büyük şoklarda fiyat düşüşünü abartır, artışı küçümser.")


def bolum_egri() -> GetiriEgrisi:
    """Örnek par tahvil kotasyonlarından spot eğri bootstrap eder."""
    baslik("3) GETİRİ EĞRİSİ: BOOTSTRAP, FORWARD, NELSON-SIEGEL")
    # Örnek piyasa: 1-10 yıl vadeli, fiyatı 100 (par) kote edilen yıllık kuponlu
    # tahviller; kupon oranı = o vadenin par getirisi.
    par_getiriler = {
        1: 0.36,
        2: 0.33,
        3: 0.305,
        4: 0.285,
        5: 0.27,
        6: 0.258,
        7: 0.249,
        8: 0.242,
        9: 0.237,
        10: 0.233,
    }
    enstrumanlar = [
        (Tahvil(nominal=100, kupon_orani=c, vade_yil=v, frekans=1, isim=f"{v}Y par"), 100.0)
        for v, c in par_getiriler.items()
    ]
    egri = GetiriEgrisi.bootstrap(enstrumanlar, temiz=True, interpolasyon="dogrusal")
    ns = nelson_siegel_uydur(egri.vadeler, egri.oranlar)

    satirlar = []
    for v in range(1, 11):
        satirlar.append(
            {
                "Vade (yıl)": v,
                "Par getiri %": par_getiriler[v] * 100,
                "Spot oran %": egri.spot_oran(v) * 100,
                "1Y forward %": egri.forward_oran(v - 1, v) * 100 if v >= 1 else float("nan"),
                "Nelson-Siegel %": ns.oran(v) * 100,
            }
        )
    tablo_yaz(pd.DataFrame(satirlar).set_index("Vade (yıl)"), ondalik=3)
    print(
        f"\nNelson-Siegel parametreleri: β0={ns.beta0:.4f}, β1={ns.beta1:.4f}, "
        f"β2={ns.beta2:.4f}, τ={ns.tau:.3f}  (RMSE={ns.rmse * 100:.4f} puan)"
    )

    ornek = Tahvil(nominal=100, kupon_orani=0.28, vade_yil=5, frekans=1, isim="5Y %28")
    print(
        f"\nSpot eğriden fiyatlama örneği — {ornek.isim} kuponlu tahvil: "
        f"{spot_egriden_fiyat(ornek, egri):,.4f}"
    )
    print("(Ters getiri eğrisi: kısa vadeli oranlar uzun vadelilerden yüksek;")
    print(" forward oranlar piyasanın gelecekte faiz düşüşü beklediğini gösterir.)")
    return egri


def bolum_stratejiler(egri: GetiriEgrisi) -> None:
    """Üç stratejiyi kurar, senaryo analizini koşar, öneri verir, grafik üretir."""
    baslik("4) STRATEJİLER: MERDİVEN / BARBELL / BULLET")
    tutar = 1_000_000.0
    merdiven = merdiven_portfoy(tutar, list(range(1, 11)), egri)
    barbell = barbell_portfoy(tutar, kisa_vade=2, uzun_vade=10, getiri=egri)
    bullet = bullet_portfoy(tutar, hedef_vade=5.5, getiri=egri)
    portfoyler = {"Merdiven": merdiven, "Barbell": barbell, "Bullet": bullet}

    satirlar = []
    for isim, p in portfoyler.items():
        satirlar.append(
            {
                "Strateji": isim,
                "Piyasa Değeri": p.toplam_deger,
                "Ağırlıklı YTM %": p.portfoy_getiri() * 100,
                "Macaulay (yıl)": p.portfoy_macaulay_durasyon(),
                "Modifiye": p.portfoy_modifiye_durasyon(),
                "Konveksite": p.portfoy_konveksite(),
            }
        )
    tablo_yaz(pd.DataFrame(satirlar).set_index("Strateji"))
    print(f"\nToplam yatırım: {tutar:,.0f} TL. Barbell 2Y+10Y (50/50), bullet 5.5Y;")
    print("üç portföyün durasyonları bilinçli olarak yakın bantta tutulmuştur ki")
    print("senaryo karşılaştırması ağırlıklı olarak eğri ŞEKLİ etkisini göstersin.")

    baslik("5) FAİZ SENARYOSU ANALİZİ")
    sonuclar = {isim: senaryo_analizi(p) for isim, p in portfoyler.items()}
    senaryo_adlari = list(standart_senaryolar().keys())
    df = pd.DataFrame(
        {
            isim: {s: sonuclar[isim][s]["degisim_yuzde"] for s in senaryo_adlari}
            for isim in portfoyler
        }
    )
    df.index.name = "Senaryo (değişim %)"
    tablo_yaz(df, ondalik=3)
    print("\nOkuma kılavuzu: Faiz artış senaryolarında tüm portföyler değer")
    print("kaybeder (negatif), düşüş senaryolarında kazanır. Dikleşmede uzun uca")
    print("yüklü barbell en çok etkilenirken, yataylaşmada avantajlıdır.")

    baslik("6) İMMÜNİZASYON (hedef ufka durasyon eşleme)")
    hedef_ufuk = 4.0
    imm = immunizasyon_portfoy(tutar, hedef_ufuk, kisa_vade=2, uzun_vade=10, getiri=egri)
    agirliklar = imm.agirliklar()
    print(f"Hedef ufuk: {hedef_ufuk:g} yıl")
    print(f"Kurulan portföy Macaulay durasyonu: {imm.portfoy_macaulay_durasyon():.4f} yıl")
    print(
        f"Ağırlıklar: kısa (2Y) %{agirliklar[0] * 100:.2f}  /  "
        f"uzun (10Y) %{agirliklar[1] * 100:.2f}"
    )
    print("Küçük paralel faiz oynamalarında fiyat ve yeniden yatırım riskleri")
    print("birbirini dengeler; ufuk sonunda hedeflenen birikim korunur.")

    baslik("7) STRATEJİ ÖNERİSİ (örnek yatırımcı profilleri)")
    profiller = [
        ("dusecek", 5.0, "orta"),
        ("yukselecek", 3.0, "dusuk"),
        ("sabit", 7.0, "yuksek"),
    ]
    for beklenti, ufuk, risk in profiller:
        oneri = strateji_oner(beklenti, ufuk, risk)
        print(f"\n• Profil: faiz beklentisi={beklenti}, ufuk={ufuk:g} yıl, risk={risk}")
        print(
            f"  Önerilen strateji : {oneri.strateji.upper()}  "
            f"(hedef durasyon ≈ {oneri.hedef_durasyon:.1f} yıl)"
        )
        print(f"  Gerekçe           : {oneri.gerekce}")

    baslik("8) GRAFİKLER (output/ klasörüne PNG)")
    ornek_tahviller = [
        Tahvil(100, 0.10, 5, 1, isim="5Y %10 kuponlu"),
        Tahvil(100, 0.0, 5, 1, isim="5Y sıfır kuponlu"),
        Tahvil(100, 0.10, 10, 1, isim="10Y %10 kuponlu"),
    ]
    ns = nelson_siegel_uydur(egri.vadeler, egri.oranlar)
    dosyalar = [
        fiyat_getiri_grafigi(ornek_tahviller, cikti_klasoru=CIKTI_KLASORU),
        getiri_egrisi_grafigi(egri, ns=ns, cikti_klasoru=CIKTI_KLASORU),
        strateji_karsilastirma_grafigi(sonuclar, cikti_klasoru=CIKTI_KLASORU),
        nakit_akisi_grafigi(list(portfoyler.values()), cikti_klasoru=CIKTI_KLASORU),
    ]
    for yol in dosyalar:
        print(f"  kaydedildi: {yol}")


def bolum_backtest(egri: GetiriEgrisi) -> BacktestKarsilastirma:
    """Strateji backtest'ini koşar, özet tabloları yazar, grafik üretir."""
    from bond_lab.backtest import backtest_grafigi, stratejileri_backtest_et

    baslik("9) STRATEJİ BACKTEST'İ (deterministik patikalar + Vasicek)")
    sonuc = stratejileri_backtest_et(egri, ufuk_yil=3.0, patika_sayisi=200, seed=42)
    print("Deterministik faiz patikalarında YILLIK getiri (%):")
    tablo_yaz(sonuc.deterministik, ondalik=3)
    print("\nVasicek simülasyonu — yıllık getiri dağılımı (%):")
    tablo_yaz(sonuc.stokastik_ozet, ondalik=3)
    print(f"\nParametreler: {sonuc.parametreler}")
    print("Okuma kılavuzu: kademeli faiz ARTIŞINDA kısa vadelere yayılan merdiven,")
    print("uzun durasyonlu bullet'tan iyi performans gösterir; DÜŞÜŞTE tersi geçerli")
    print("olur. Vasicek dağılımında bullet'ın standart sapması (riski) en yüksektir.")
    yol = backtest_grafigi(sonuc, cikti_klasoru=CIKTI_KLASORU)
    print(f"\n  kaydedildi: {yol}")
    return sonuc


def bolum_rapor(backtest_sonucu: BacktestKarsilastirma | None = None) -> None:
    """Örnek analiz sonuçlarını Excel + CSV rapora yazar."""
    from bond_lab.market_data import dibs_ornek_egrisi, ornek_csvleri_yaz
    from bond_lab.report import fiyatlama_tablosu, rapor_uret, senaryo_tablosu

    baslik("10) RAPOR (Excel + CSV, output/ klasörüne)")
    ornek_tahviller = [
        Tahvil(100, 0.25, 2, 1, isim="2Y %25 kuponlu"),
        Tahvil(100, 0.22, 5, 2, isim="5Y %22 6 aylık"),
        Tahvil(100, 0.0, 10, 1, isim="10Y sıfır kuponlu"),
    ]
    fiyatlama_df = fiyatlama_tablosu(ornek_tahviller, [0.30, 0.27, 0.24])

    egri = dibs_ornek_egrisi().spot_egri()
    tutar = 1_000_000.0
    portfoyler = {
        "Merdiven": merdiven_portfoy(tutar, list(range(1, 8)), egri),
        "Barbell": barbell_portfoy(tutar, kisa_vade=1, uzun_vade=7, getiri=egri),
        "Bullet": bullet_portfoy(tutar, hedef_vade=5, getiri=egri),
    }
    senaryo_df = senaryo_tablosu({isim: senaryo_analizi(p) for isim, p in portfoyler.items()})
    yollar = rapor_uret(
        fiyatlama=fiyatlama_df,
        portfoyler=portfoyler,
        senaryolar=senaryo_df,
        backtest_deterministik=(
            backtest_sonucu.deterministik if backtest_sonucu is not None else None
        ),
        backtest_ozet=(backtest_sonucu.stokastik_ozet if backtest_sonucu is not None else None),
        cikti_klasoru=CIKTI_KLASORU,
    )
    veri_yollari = ornek_csvleri_yaz(Path(__file__).resolve().parent / "data")
    print(f"Excel raporu : {yollar['excel'][0]}")
    for yol in yollar["csv"]:
        print(f"CSV          : {yol}")
    for yol in veri_yollari:
        print(f"Örnek veri   : {yol}")
    print("\n(Raporda: fiyatlama özeti, portföy dökümleri, senaryo analizi ve")
    print(" backtest tabloları ayrı Excel sayfalarında, Türkçe başlıklarla yer alır.)")


def demo() -> None:
    """Uçtan uca tam demo."""
    print("TAHVİL DEĞERLEME VE STRATEJİ ANALİZİ — DEMO")
    print("(Tüm oranlar yıllık bileşiktir; fiyatlar 100 nominal üzerindendir.)")
    tahviller = bolum_fiyatlama()
    bolum_risk(tahviller)
    egri = bolum_egri()
    bolum_stratejiler(egri)
    backtest_sonucu = bolum_backtest(egri)
    bolum_rapor(backtest_sonucu)
    baslik("DEMO TAMAMLANDI")
    print(f"Grafikler ve raporlar: {CIKTI_KLASORU}")
    print("Web arayüzü için: .venv\\Scripts\\python.exe main.py web")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def cli_fiyatla(args: argparse.Namespace) -> None:
    """`fiyatla` alt komutu: tek tahvili fiyatlar ve ölçütleri yazar."""
    tahvil = Tahvil(
        nominal=args.nominal,
        kupon_orani=args.kupon,
        vade_yil=args.vade,
        frekans=args.frekans,
        isim="Kullanıcı tahvili",
    )
    ytm = args.ytm
    print(f"\n{tahvil}")
    print(f"  YTM                : %{ytm * 100:.4f}")
    print(f"  Kirli fiyat        : {kirli_fiyat(tahvil, ytm):,.6f}")
    print(f"  İşlemiş faiz       : {tahvil.islemis_faiz():,.6f}")
    print(f"  Temiz fiyat        : {temiz_fiyat(tahvil, ytm):,.6f}")
    tf = temiz_fiyat(tahvil, ytm)
    if tf > 0 and not tahvil.sifir_kuponlu:
        print(f"  Cari getiri        : %{cari_getiri(tahvil, tf) * 100:.4f}")
    print(f"  Macaulay durasyonu : {macaulay_durasyon(tahvil, ytm):.6f} yıl")
    print(f"  Modifiye durasyon  : {modifiye_durasyon(tahvil, ytm):.6f}")
    print(f"  DV01               : {dv01(tahvil, ytm):.6f}")
    print(f"  Konveksite         : {konveksite(tahvil, ytm):.6f}")


def cli_oner(args: argparse.Namespace) -> None:
    """`oner` alt komutu: profile göre strateji önerisi yazar."""
    oneri = strateji_oner(args.beklenti, args.ufuk, args.risk)
    print(f"\nÖnerilen strateji : {oneri.strateji.upper()}")
    print(f"Hedef durasyon    : {oneri.hedef_durasyon:.1f} yıl")
    print(f"Gerekçe           : {oneri.gerekce}")


def cli_backtest(args: argparse.Namespace) -> None:
    """`backtest` alt komutu: DİBS örnek eğrisiyle strateji backtest'i."""
    from bond_lab.backtest import backtest_grafigi, stratejileri_backtest_et
    from bond_lab.market_data import dibs_ornek_egrisi

    egri = dibs_ornek_egrisi().spot_egri()
    sonuc = stratejileri_backtest_et(
        egri, ufuk_yil=args.ufuk, patika_sayisi=args.patika, seed=args.seed
    )
    print("\nDeterministik faiz patikalarında YILLIK getiri (%):")
    tablo_yaz(sonuc.deterministik, ondalik=3)
    print("\nVasicek simülasyonu — yıllık getiri dağılımı (%):")
    tablo_yaz(sonuc.stokastik_ozet, ondalik=3)
    print(f"\nParametreler: {sonuc.parametreler}")
    yol = backtest_grafigi(sonuc, cikti_klasoru=CIKTI_KLASORU)
    print(f"Grafik: {yol}")


def cli_rapor(_args: argparse.Namespace) -> None:
    """`rapor` alt komutu: örnek analizden Excel + CSV raporu üretir."""
    bolum_rapor()


def cli_web(_args: argparse.Namespace) -> None:
    """`web` alt komutu: Streamlit arayüzünü bu Python ortamıyla başlatır."""
    import subprocess

    app_yolu = Path(__file__).resolve().parent / "app.py"
    print("Streamlit arayüzü başlatılıyor... (durdurmak için Ctrl+C)")
    print(f"Komut: {sys.executable} -m streamlit run {app_yolu}")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_yolu)], check=False)


def main(argv: list[str] | None = None) -> None:
    """Komut satırı girişi; argümansız çalıştırılırsa tam demoyu koşar."""
    _konsolu_utf8_yap()
    ayristirici = argparse.ArgumentParser(
        prog="main.py",
        description="Tahvil değerleme ve strateji analizi (Türkçe demo/CLI).",
    )
    altlar = ayristirici.add_subparsers(dest="komut")

    altlar.add_parser("demo", help="Uçtan uca tam demoyu çalıştır (varsayılan).")

    p_fiyatla = altlar.add_parser("fiyatla", help="Tek tahvili fiyatla.")
    p_fiyatla.add_argument(
        "--nominal", type=float, default=100.0, help="Nominal değer (varsayılan 100)."
    )
    p_fiyatla.add_argument(
        "--kupon", type=float, required=True, help="Yıllık kupon oranı, ondalık (0.10 = %%10)."
    )
    p_fiyatla.add_argument("--vade", type=float, required=True, help="Vade (yıl).")
    p_fiyatla.add_argument("--ytm", type=float, required=True, help="Yıllık getiri, ondalık.")
    p_fiyatla.add_argument(
        "--frekans", type=int, default=1, choices=[1, 2, 4, 12], help="Yılda kupon sayısı."
    )

    p_oner = altlar.add_parser("oner", help="Profile göre strateji önerisi al.")
    p_oner.add_argument(
        "--beklenti",
        required=True,
        choices=["yukselecek", "dusecek", "sabit"],
        help="Faiz beklentisi.",
    )
    p_oner.add_argument("--ufuk", type=float, required=True, help="Yatırım ufku (yıl).")
    p_oner.add_argument(
        "--risk", required=True, choices=["dusuk", "orta", "yuksek"], help="Risk toleransı."
    )

    p_backtest = altlar.add_parser(
        "backtest", help="Strateji backtest'ini koş (merdiven/barbell/bullet)."
    )
    p_backtest.add_argument(
        "--ufuk", type=float, default=3.0, help="Backtest ufku, yıl (varsayılan 3)."
    )
    p_backtest.add_argument(
        "--patika", type=int, default=200, help="Vasicek patika sayısı (varsayılan 200)."
    )
    p_backtest.add_argument(
        "--seed", type=int, default=42, help="Rastgelelik tohumu (varsayılan 42)."
    )

    altlar.add_parser("rapor", help="Örnek analizden Excel + CSV raporu üret (output/).")
    altlar.add_parser("web", help="Streamlit web arayüzünü başlat (app.py).")

    args = ayristirici.parse_args(argv)
    if args.komut == "fiyatla":
        cli_fiyatla(args)
    elif args.komut == "oner":
        cli_oner(args)
    elif args.komut == "backtest":
        cli_backtest(args)
    elif args.komut == "rapor":
        cli_rapor(args)
    elif args.komut == "web":
        cli_web(args)
    else:
        demo()


if __name__ == "__main__":
    main()
