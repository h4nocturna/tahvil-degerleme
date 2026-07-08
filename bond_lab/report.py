"""Raporlama: analiz sonuçlarını Excel (çok sayfalı) ve CSV'lere yazar.

Tek giriş noktası :func:`rapor_uret`:

    * Fiyatlama özeti, portföy dökümü, senaryo analizi ve backtest
      sonuçlarını tek bir Excel dosyasına (``openpyxl`` motoru, her tablo
      ayrı sayfada, Türkçe sayfa adları ve başlıklar) yazar.
    * Aynı tabloları tek tek CSV olarak da (UTF-8 BOM'lu; Excel'de Türkçe
      karakterler doğru görünsün diye ``utf-8-sig``) kaydeder.
    * Yazılan her dosyanın gerçekten oluştuğunu doğrular; oluşmayanlar
      için :class:`RuntimeError` fırlatır.

Tablo üretici yardımcılar (``fiyatlama_tablosu``, ``portfoy_tablosu``,
``senaryo_tablosu``) çekirdek modüllerin çıktısını raporlanabilir
``pandas.DataFrame``'lere çevirir.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pandas as pd

from bond_lab.bond import Tahvil
from bond_lab.portfolio import Portfoy
from bond_lab.pricing import cari_getiri, kirli_fiyat, temiz_fiyat
from bond_lab.risk import dv01, konveksite, macaulay_durasyon, modifiye_durasyon

VARSAYILAN_CIKTI = Path("output")

#: Excel sayfa adı en çok 31 karakter olabilir (openpyxl kısıtı).
_SAYFA_AD_SINIRI = 31


# ----------------------------------------------------------------------
# Tablo üreticiler
# ----------------------------------------------------------------------
def fiyatlama_tablosu(tahviller: Sequence[Tahvil], ytmler: Sequence[float]) -> pd.DataFrame:
    """Tahvil listesi için fiyat/risk özeti tablosu (Türkçe başlıklar).

    Args:
        tahviller: Tahviller.
        ytmler: Her tahvile karşılık gelen yıllık getiri.

    Raises:
        ValueError: Liste uzunlukları eşleşmiyorsa.
    """
    if len(tahviller) != len(ytmler):
        raise ValueError("Tahvil ve YTM listeleri aynı uzunlukta olmalıdır.")
    satirlar: list[dict[str, object]] = []
    for tahvil, ytm in zip(tahviller, ytmler, strict=True):
        tf = temiz_fiyat(tahvil, ytm)
        satirlar.append(
            {
                "Tahvil": tahvil.isim or str(tahvil),
                "Vade (yıl)": tahvil.vade_yil,
                "Kupon %": tahvil.kupon_orani * 100,
                "Frekans": tahvil.frekans,
                "YTM %": ytm * 100,
                "Kirli Fiyat": kirli_fiyat(tahvil, ytm),
                "Temiz Fiyat": tf,
                "İşlemiş Faiz": tahvil.islemis_faiz(),
                "Cari Getiri %": (cari_getiri(tahvil, tf) * 100 if tf > 0 else 0.0),
                "Macaulay (yıl)": macaulay_durasyon(tahvil, ytm),
                "Modifiye Durasyon": modifiye_durasyon(tahvil, ytm),
                "DV01": dv01(tahvil, ytm),
                "Konveksite": konveksite(tahvil, ytm),
            }
        )
    return pd.DataFrame(satirlar)


def portfoy_tablosu(portfoy: Portfoy) -> pd.DataFrame:
    """Portföy pozisyon dökümü tablosu (Türkçe başlıklar)."""
    satirlar: list[dict[str, object]] = []
    toplam = portfoy.toplam_deger
    for poz in portfoy.pozisyonlar:
        deger = poz.piyasa_degeri
        satirlar.append(
            {
                "Pozisyon": poz.tahvil.isim or str(poz.tahvil),
                "Vade (yıl)": poz.tahvil.vade_yil,
                "Kupon %": poz.tahvil.kupon_orani * 100,
                "Adet": poz.adet,
                "YTM %": poz.ytm * 100,
                "Birim Fiyat": poz.birim_fiyat,
                "Piyasa Değeri": deger,
                "Ağırlık %": (deger / toplam * 100 if toplam > 0 else 0.0),
                "Macaulay (yıl)": macaulay_durasyon(poz.tahvil, poz.ytm),
            }
        )
    return pd.DataFrame(satirlar)


def senaryo_tablosu(senaryo_sonuclari: dict[str, dict[str, dict[str, float]]]) -> pd.DataFrame:
    """Senaryo analizi sonuçlarını tek tabloya çevirir.

    Args:
        senaryo_sonuclari: ``{strateji: {senaryo: {"degisim_yuzde": ...}}}``
            biçiminde :func:`bond_lab.strategies.senaryo_analizi` çıktıları.

    Returns:
        Satır=senaryo, sütun=strateji, hücre=değişim yüzdesi.
    """
    df = pd.DataFrame(
        {
            strateji: {senaryo: sonuc["degisim_yuzde"] for senaryo, sonuc in senaryolar.items()}
            for strateji, senaryolar in senaryo_sonuclari.items()
        }
    )
    df.index.name = "Senaryo (değişim %)"
    return df


# ----------------------------------------------------------------------
# Dosya yazıcılar
# ----------------------------------------------------------------------
def _dosya_dogrula(yollar: Sequence[Path]) -> None:
    """Dosyaların diskte oluştuğunu ve boş olmadığını doğrular."""
    eksikler = [str(y) for y in yollar if not (Path(y).exists() and Path(y).stat().st_size > 0)]
    if eksikler:
        raise RuntimeError(f"Rapor dosyaları oluşturulamadı: {', '.join(eksikler)}")


def _sayfa_adi(ad: str) -> str:
    """Excel sayfa adını openpyxl kurallarına uydurur (<=31 kr, yasak kr yok)."""
    temiz = ad
    for kr in r"[]:*?/\\":
        temiz = temiz.replace(kr, "-")
    return temiz[:_SAYFA_AD_SINIRI]


def excele_yaz(
    tablolar: dict[str, pd.DataFrame],
    dosya_adi: str = "tahvil_raporu.xlsx",
    cikti_klasoru: Path | None = None,
) -> Path:
    """Tabloları tek Excel dosyasına, her tabloyu ayrı sayfaya yazar.

    Args:
        tablolar: Sayfa adı → DataFrame eşlemesi (Türkçe adlar desteklenir).
        dosya_adi: Excel dosya adı.
        cikti_klasoru: Hedef klasör (None ise ``output/``).

    Returns:
        Yazılan dosyanın yolu (varlığı doğrulanmış).

    Raises:
        ValueError: Tablo sözlüğü boşsa.
        RuntimeError: Dosya oluşturulamadıysa.
    """
    if not tablolar:
        raise ValueError("Yazılacak en az bir tablo gereklidir.")
    klasor = Path(cikti_klasoru) if cikti_klasoru is not None else VARSAYILAN_CIKTI
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / dosya_adi
    with pd.ExcelWriter(yol, engine="openpyxl") as yazici:
        for ad, df in tablolar.items():
            indeks_yaz = df.index.name is not None
            df.to_excel(yazici, sheet_name=_sayfa_adi(ad), index=indeks_yaz)
    _dosya_dogrula([yol])
    return yol


def csvlere_yaz(
    tablolar: dict[str, pd.DataFrame],
    on_ek: str = "rapor",
    cikti_klasoru: Path | None = None,
) -> list[Path]:
    """Her tabloyu ayrı CSV dosyasına yazar (``utf-8-sig``).

    Dosya adları ``{on_ek}_{sayfa_adi}.csv`` kalıbıyla, Türkçe karakterler
    ve boşluklar ASCII'ye/alt çizgiye sadeleştirilerek üretilir.

    Returns:
        Yazılan dosya yolları (varlıkları doğrulanmış).
    """
    klasor = Path(cikti_klasoru) if cikti_klasoru is not None else VARSAYILAN_CIKTI
    klasor.mkdir(parents=True, exist_ok=True)
    cevrim = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosuCGIOSU_")
    yollar: list[Path] = []
    for ad, df in tablolar.items():
        guvenli = ad.translate(cevrim).lower()
        guvenli = "".join(kr for kr in guvenli if kr.isalnum() or kr == "_")
        yol = klasor / f"{on_ek}_{guvenli}.csv"
        df.to_csv(yol, index=df.index.name is not None, encoding="utf-8-sig")
        yollar.append(yol)
    _dosya_dogrula(yollar)
    return yollar


def rapor_uret(
    fiyatlama: pd.DataFrame | None = None,
    portfoyler: dict[str, Portfoy] | None = None,
    senaryolar: pd.DataFrame | None = None,
    backtest_deterministik: pd.DataFrame | None = None,
    backtest_ozet: pd.DataFrame | None = None,
    dosya_adi: str = "tahvil_raporu.xlsx",
    cikti_klasoru: Path | None = None,
    csv_de_yaz: bool = True,
) -> dict[str, list[Path]]:
    """Verilen bölümlerden tam rapor üretir (Excel + opsiyonel CSV'ler).

    En az bir bölüm verilmelidir; verilmeyen bölümler atlanır. Excel'e
    ayrıca rapor tarihi ve içerik listesini gösteren "Özet" sayfası eklenir.

    Args:
        fiyatlama: :func:`fiyatlama_tablosu` çıktısı.
        portfoyler: İsim→portföy; her biri ayrı sayfa olur.
        senaryolar: :func:`senaryo_tablosu` çıktısı.
        backtest_deterministik: Deterministik backtest tablosu.
        backtest_ozet: Vasicek özet istatistik tablosu.
        dosya_adi: Excel dosya adı.
        cikti_klasoru: Hedef klasör (None ise ``output/``).
        csv_de_yaz: True ise tablolar CSV olarak da kaydedilir.

    Returns:
        ``{"excel": [yol], "csv": [yollar]}`` sözlüğü.

    Raises:
        ValueError: Hiç bölüm verilmemişse.
        RuntimeError: Dosyalar oluşturulamadıysa.
    """
    tablolar: dict[str, pd.DataFrame] = {}
    if fiyatlama is not None:
        tablolar["Fiyatlama"] = fiyatlama
    if portfoyler:
        for isim, p in portfoyler.items():
            tablolar[f"Portföy - {isim}"] = portfoy_tablosu(p)
    if senaryolar is not None:
        tablolar["Senaryo Analizi"] = senaryolar
    if backtest_deterministik is not None:
        tablolar["Backtest - Patikalar"] = backtest_deterministik
    if backtest_ozet is not None:
        tablolar["Backtest - Simülasyon"] = backtest_ozet
    if not tablolar:
        raise ValueError("Rapor için en az bir bölüm verilmelidir.")

    ozet = pd.DataFrame(
        {
            "Alan": ["Rapor tarihi", "İçerik"],
            "Değer": [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                ", ".join(tablolar.keys()),
            ],
        }
    )
    excel_tablolari = {"Özet": ozet, **tablolar}

    excel_yolu = excele_yaz(excel_tablolari, dosya_adi=dosya_adi, cikti_klasoru=cikti_klasoru)
    sonuc: dict[str, list[Path]] = {"excel": [excel_yolu], "csv": []}
    if csv_de_yaz:
        sonuc["csv"] = csvlere_yaz(tablolar, cikti_klasoru=cikti_klasoru)
    return sonuc
