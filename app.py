"""Tahvil Laboratuvarı — Streamlit web arayüzü (Türkçe).

Başlatma:
    .venv\\Scripts\\python.exe -m streamlit run app.py

Sekmeler:
    1. Tahvil Fiyatlama   — fiyat/YTM, durasyon, konveksite, DV01, grafik.
    2. Getiri Eğrisi      — örnek/CSV/FRED verisinden spot + forward eğri,
                            Nelson-Siegel uydurma.
    3. Portföy ve Stratejiler — merdiven/barbell/bullet kurulumu, metrik
                            karşılaştırması, gerekçeli strateji önerisi.
    4. Senaryo ve Backtest — paralel kayma senaryoları + backtest motoru.
    5. Rapor              — Excel raporu üretme ve indirme.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bond_lab import (
    GetiriEgrisi,
    Tahvil,
    barbell_portfoy,
    bullet_portfoy,
    dv01,
    kirli_fiyat,
    konveksite,
    macaulay_durasyon,
    merdiven_portfoy,
    modifiye_durasyon,
    nelson_siegel_uydur,
    senaryo_analizi,
    strateji_oner,
    temiz_fiyat,
    ytm_bul,
)
from bond_lab.backtest import backtest_grafigi, stratejileri_backtest_et
from bond_lab.market_data import (
    ORNEK_VERI_UYARISI,
    dibs_ornek_egrisi,
    egriyi_csvden_yukle,
    fred_hazine_egrisi,
    ust_ornek_egrisi,
)
from bond_lab.report import fiyatlama_tablosu, rapor_uret, senaryo_tablosu

CIKTI_KLASORU = Path(__file__).resolve().parent / "output"

BEKLENTI_ETIKETLERI = {"yukselecek": "Yükselecek", "dusecek": "Düşecek", "sabit": "Sabit kalacak"}
RISK_ETIKETLERI = {"dusuk": "Düşük", "orta": "Orta", "yuksek": "Yüksek"}

st.set_page_config(page_title="Tahvil Laboratuvarı", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
    div[data-testid="stPlotlyChart"],
    div[data-testid="stPlotlyChart"] .js-plotly-plot,
    div[data-testid="stPlotlyChart"] .plot-container,
    div[data-testid="stPlotlyChart"] .svg-container,
    div[data-testid="stPlotlyChart"] .main-svg {
        background: transparent !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Tahvil Laboratuvarı")
st.caption(
    "Tahvil fiyatlama, getiri eğrisi, portföy stratejileri, backtest ve raporlama — "
    "bond_lab paketi üzerine Türkçe web arayüzü."
)

sekme_fiyat, sekme_egri, sekme_portfoy, sekme_senaryo, sekme_rapor = st.tabs(
    [
        "Tahvil Fiyatlama",
        "Getiri Eğrisi",
        "Portföy ve Stratejiler",
        "Senaryo ve Backtest",
        "Rapor",
    ]
)


# ----------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def _fred_egrisi_onbellekli():
    """FRED eğrisini saatlik önbellekle çeker; başarısızsa None."""
    return fred_hazine_egrisi(zaman_asimi=20.0)


def _fiyat_getiri_tablosu(
    tahvil: Tahvil,
    ytm: float,
    *,
    adim_yuzde: float = 0.5,
    bant_yuzde: float = 15.0,
) -> pd.DataFrame:
    """Mevcut YTM etrafında fiyat–getiri eğrisini tablo olarak üretir."""
    merkez = ytm * 100.0
    alt = max(0.01, merkez - bant_yuzde)
    ust = merkez + bant_yuzde
    ytm_yuzdeleri = np.arange(alt, ust + adim_yuzde / 2, adim_yuzde)

    mevcut_kirli = kirli_fiyat(tahvil, ytm)
    satirlar: list[dict[str, float | bool]] = []
    for y_pct in ytm_yuzdeleri:
        y_dec = float(y_pct) / 100.0
        try:
            kirli = kirli_fiyat(tahvil, y_dec)
            temiz = temiz_fiyat(tahvil, y_dec)
        except ValueError:
            continue
        satirlar.append(
            {
                "YTM (%)": float(y_pct),
                "Kirli Fiyat": kirli,
                "Temiz Fiyat": temiz,
                "Fiyat Farkı (%)": (kirli - mevcut_kirli) / mevcut_kirli * 100.0,
                "Mevcut": abs(float(y_pct) - merkez) < adim_yuzde / 2,
            }
        )
    return pd.DataFrame(satirlar)


def _streamlit_tema_renkleri() -> dict[str, str]:
    """Streamlit temasından grafik renklerini okur (açık/koyu uyumlu)."""
    theme = st.context.theme
    koyu = theme.get("base", "light") == "dark"
    return {
        "metin": theme.get("textColor", "#FAFAFA" if koyu else "#31333F"),
        "birincil": theme.get("primaryColor", "#FF4B4B"),
        "izgara": "rgba(250, 250, 250, 0.14)" if koyu else "rgba(49, 51, 63, 0.14)",
    }


def _fiyat_getiri_grafigi_ciz(tahvil: Tahvil, ytm: float, kirli: float) -> None:
    """Etkileşimli, şeffaf arka planlı fiyat–getiri grafiğini siteye gömer."""
    renkler = _streamlit_tema_renkleri()
    y_izgara = np.linspace(max(0.001, ytm - 0.15), ytm + 0.15, 120)
    ytm_yuzde = y_izgara * 100.0
    kirli_fiyatlar = [kirli_fiyat(tahvil, float(y)) for y in y_izgara]
    temiz_fiyatlar = [temiz_fiyat(tahvil, float(y)) for y in y_izgara]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=ytm_yuzde,
            y=kirli_fiyatlar,
            mode="lines",
            name="Kirli fiyat",
            line=dict(color=renkler["birincil"], width=2.5),
            customdata=np.column_stack([temiz_fiyatlar]),
            hovertemplate=(
                "YTM: %{x:.2f}%<br>"
                "Kirli fiyat: %{y:.4f}<br>"
                "Temiz fiyat: %{customdata[0]:.4f}"
                "<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[ytm * 100.0],
            y=[kirli],
            mode="markers",
            name="Mevcut YTM",
            marker=dict(
                color=renkler["birincil"],
                size=11,
                line=dict(width=2, color=renkler["metin"]),
            ),
            hovertemplate="Mevcut YTM: %{x:.2f}%<br>Kirli fiyat: %{y:.4f}<extra></extra>",
        )
    )

    fig.update_layout(
        title=dict(text="Fiyat–getiri eğrisi", font=dict(color=renkler["metin"], size=14)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=renkler["metin"]),
        margin=dict(l=8, r=8, t=40, b=8),
        height=420,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(
            title="YTM (%)",
            color=renkler["metin"],
            showgrid=True,
            gridcolor=renkler["izgara"],
            zeroline=False,
        ),
        yaxis=dict(
            title="Kirli fiyat",
            color=renkler["metin"],
            showgrid=True,
            gridcolor=renkler["izgara"],
            zeroline=False,
        ),
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
            "scrollZoom": True,
        },
    )


def _egri_sec(anahtar: str) -> tuple[GetiriEgrisi, str]:
    """Veri kaynağı seçtirip (eğri, açıklama) döndürür."""
    kaynak = st.radio(
        "Veri kaynağı",
        ["Türkiye DİBS (temsili)", "ABD Hazine (temsili)", "ABD Hazine (FRED canlı)", "CSV yükle"],
        horizontal=True,
        key=f"kaynak_{anahtar}",
    )
    if kaynak == "Türkiye DİBS (temsili)":
        p = dibs_ornek_egrisi()
        return p.spot_egri(), f"{p.kaynak} — tarih: {p.tarih}"
    if kaynak == "ABD Hazine (temsili)":
        p = ust_ornek_egrisi()
        return p.spot_egri(), f"{p.kaynak} — tarih: {p.tarih}"
    if kaynak == "ABD Hazine (FRED canlı)":
        p = _fred_egrisi_onbellekli()
        if p is None:
            st.warning("FRED'e ulaşılamadı; temsili ABD Hazine eğrisi kullanılıyor.")
            p = ust_ornek_egrisi()
        return p.spot_egri(), f"{p.kaynak} — tarih: {p.tarih}"
    yukleme = st.file_uploader(
        "CSV yükleyin (sütunlar: vade_yil, oran)", type="csv", key=f"csv_{anahtar}"
    )
    if yukleme is None:
        st.info("CSV bekleniyor; bu sırada temsili DİBS eğrisi gösteriliyor.")
        p = dibs_ornek_egrisi()
        return p.spot_egri(), f"{p.kaynak} — tarih: {p.tarih}"
    gecici = CIKTI_KLASORU / "_yuklenen_egri.csv"
    gecici.parent.mkdir(parents=True, exist_ok=True)
    gecici.write_bytes(yukleme.getvalue())
    p = egriyi_csvden_yukle(gecici)
    return p.spot_egri(), p.kaynak


# ----------------------------------------------------------------------
# 1) Tahvil Fiyatlama
# ----------------------------------------------------------------------
with sekme_fiyat:
    st.subheader("Tek Tahvil Fiyatlama ve Risk Ölçütleri")
    col1, col2, col3 = st.columns(3)
    with col1:
        nominal = st.number_input("Nominal değer", min_value=1.0, value=100.0, step=10.0)
        kupon_yuzde = st.number_input("Yıllık kupon oranı (%)", min_value=0.0, value=25.0, step=0.5)
    with col2:
        vade = st.number_input("Vade (yıl)", min_value=0.05, value=5.0, step=0.25)
        frekans = st.selectbox("Kupon frekansı (yılda)", [1, 2, 4, 12], index=0)
    with col3:
        mod = st.radio("Girdi türü", ["YTM'den fiyat", "Fiyattan YTM"])
        if mod == "YTM'den fiyat":
            ytm_yuzde = st.number_input("YTM (%)", min_value=-50.0, value=30.0, step=0.5)
        else:
            fiyat_girdi = st.number_input("Temiz fiyat", min_value=0.01, value=95.0, step=0.5)

    tahvil = Tahvil(
        nominal=nominal,
        kupon_orani=kupon_yuzde / 100.0,
        vade_yil=vade,
        frekans=int(frekans),
        isim="Kullanıcı tahvili",
    )
    try:
        if mod == "YTM'den fiyat":
            ytm = ytm_yuzde / 100.0
        else:
            ytm = ytm_bul(tahvil, fiyat_girdi, temiz=True)
        kirli = kirli_fiyat(tahvil, ytm)
        temiz = temiz_fiyat(tahvil, ytm)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Temiz fiyat", f"{temiz:,.4f}")
        m2.metric("Kirli fiyat", f"{kirli:,.4f}")
        m3.metric("YTM", f"%{ytm * 100:,.4f}")
        m4.metric("İşlemiş faiz", f"{tahvil.islemis_faiz():,.4f}")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Macaulay durasyonu", f"{macaulay_durasyon(tahvil, ytm):,.4f} yıl")
        r2.metric("Modifiye durasyon", f"{modifiye_durasyon(tahvil, ytm):,.4f}")
        r3.metric("DV01", f"{dv01(tahvil, ytm):,.6f}")
        r4.metric("Konveksite", f"{konveksite(tahvil, ytm):,.4f}")

        baslik_col, gecis_col = st.columns([3, 1])
        with baslik_col:
            st.markdown("**Fiyat–getiri analizi**")
        with gecis_col:
            gorunum = st.segmented_control(
                "Görünüm",
                options=["Grafik", "Tablo"],
                default="Grafik",
                key="fiyat_getiri_gorunum",
                label_visibility="collapsed",
            )

        if gorunum == "Grafik":
            st.caption(
                "Fareyle üzerine gelin, sürükleyerek yakınlaştırın; çift tıklayarak sıfırlayın. "
                "Mevcut YTM noktası işaretli."
            )
            _fiyat_getiri_grafigi_ciz(tahvil, ytm, kirli)
        else:
            t1, t2 = st.columns([3, 1])
            with t2:
                adim = st.select_slider(
                    "YTM adımı (%)",
                    options=[0.25, 0.5, 1.0, 2.0],
                    value=0.5,
                    key="fiyat_getiri_adim",
                )
            with t1:
                st.caption(
                    "Mevcut YTM satırı işaretli. Sütun başlıklarına tıklayarak sıralayın; "
                    "satır seçerek detay görün."
                )

            df_fiyat_getiri = _fiyat_getiri_tablosu(tahvil, ytm, adim_yuzde=float(adim))
            secim = st.dataframe(
                df_fiyat_getiri,
                column_config={
                    "YTM (%)": st.column_config.NumberColumn(
                        "YTM (%)",
                        help="Vadeye kadar getiri",
                        format="%.2f",
                    ),
                    "Kirli Fiyat": st.column_config.NumberColumn(
                        "Kirli Fiyat",
                        help="İşlemiş faiz dahil fiyat",
                        format="%.4f",
                    ),
                    "Temiz Fiyat": st.column_config.NumberColumn(
                        "Temiz Fiyat",
                        help="İşlemiş faiz hariç fiyat",
                        format="%.4f",
                    ),
                    "Fiyat Farkı (%)": st.column_config.NumberColumn(
                        "Fiyat Farkı (%)",
                        help="Mevcut YTM fiyatına göre değişim",
                        format="%+.2f",
                    ),
                    "Mevcut": st.column_config.CheckboxColumn(
                        "Mevcut",
                        help="Girdiğiniz YTM satırı",
                        disabled=True,
                    ),
                },
                hide_index=True,
                width="stretch",
                height=420,
                on_select="rerun",
                selection_mode="single-row",
                key="fiyat_getiri_tablosu",
            )

            if secim.selection.rows:
                satir = df_fiyat_getiri.iloc[secim.selection.rows[0]]
                st.info(
                    f"**Seçilen senaryo:** YTM %{satir['YTM (%)']:.2f} → "
                    f"kirli fiyat **{satir['Kirli Fiyat']:.4f}** "
                    f"(mevcut YTM'e göre **{satir['Fiyat Farkı (%)']:+.2f}%**)"
                )
            else:
                mevcut_satir = df_fiyat_getiri.loc[df_fiyat_getiri["Mevcut"]]
                if not mevcut_satir.empty:
                    satir = mevcut_satir.iloc[0]
                    st.caption(
                        f"Mevcut nokta: YTM %{satir['YTM (%)']:.2f}, "
                        f"kirli fiyat {satir['Kirli Fiyat']:.4f}"
                    )
    except ValueError as hata:
        st.error(f"Hesaplama hatası: {hata}")


# ----------------------------------------------------------------------
# 2) Getiri Eğrisi
# ----------------------------------------------------------------------
with sekme_egri:
    st.subheader("Spot ve Forward Getiri Eğrisi")
    egri, kaynak_notu = _egri_sec("egri")
    st.caption(f"Kaynak: {kaynak_notu}")

    t_izgara = np.linspace(float(egri.vadeler[0]), float(egri.vadeler[-1]), 200)
    spotlar = [egri.spot_oran(float(t)) * 100 for t in t_izgara]

    ns = None
    if len(egri.vadeler) >= 4:
        ns = nelson_siegel_uydur(egri.vadeler, egri.oranlar)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(t_izgara, spotlar, label="Spot eğri", linewidth=2)
    ax.scatter(egri.vadeler, egri.oranlar * 100, color="crimson", zorder=5, label="Gözlem")
    fwd_t = [float(t) for t in t_izgara if t + 1.0 <= float(egri.vadeler[-1])]
    if fwd_t:
        ax.plot(
            fwd_t,
            [egri.forward_oran(t, t + 1.0) * 100 for t in fwd_t],
            "--",
            label="1Y forward",
            linewidth=1.8,
        )
    if ns is not None:
        ax.plot(
            t_izgara,
            [ns.oran(float(t)) * 100 for t in t_izgara],
            ":",
            label="Nelson-Siegel",
            linewidth=2,
        )
    ax.set_xlabel("Vade (yıl)")
    ax.set_ylabel("Oran (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    plt.close(fig)

    if ns is not None:
        st.markdown(
            f"**Nelson-Siegel parametreleri:** β₀={ns.beta0:.4f}, β₁={ns.beta1:.4f}, "
            f"β₂={ns.beta2:.4f}, τ={ns.tau:.3f} (RMSE={ns.rmse * 100:.4f} puan)"
        )
    df_egri = pd.DataFrame(
        {"Vade (yıl)": egri.vadeler, "Spot oran %": egri.oranlar * 100}
    ).set_index("Vade (yıl)")
    st.dataframe(df_egri.style.format("{:.3f}"), width="stretch")


# ----------------------------------------------------------------------
# 3) Portföy ve Stratejiler
# ----------------------------------------------------------------------
with sekme_portfoy:
    st.subheader("Strateji Portföyleri ve Öneri Motoru")
    egri_p, kaynak_notu_p = _egri_sec("portfoy")
    st.caption(f"Kaynak: {kaynak_notu_p}")

    tutar = st.number_input(
        "Toplam yatırım tutarı", min_value=1_000.0, value=1_000_000.0, step=100_000.0
    )
    maks_vade = float(egri_p.vadeler[-1])
    c1, c2, c3 = st.columns(3)
    with c1:
        merdiven_maks = st.slider(
            "Merdiven: son basamak (yıl)", 2, int(max(maks_vade, 2)), int(min(10, maks_vade))
        )
    with c2:
        barbell_kisa = st.number_input("Barbell: kısa vade (yıl)", 0.25, maks_vade, 2.0, 0.25)
        barbell_uzun = st.number_input(
            "Barbell: uzun vade (yıl)", barbell_kisa + 0.25, maks_vade, min(10.0, maks_vade), 0.25
        )
    with c3:
        bullet_vade = st.number_input(
            "Bullet: hedef vade (yıl)", 0.25, maks_vade, min(5.0, maks_vade), 0.25
        )

    try:
        portfoyler = {
            "Merdiven": merdiven_portfoy(tutar, list(range(1, merdiven_maks + 1)), egri_p),
            "Barbell": barbell_portfoy(tutar, barbell_kisa, barbell_uzun, egri_p),
            "Bullet": bullet_portfoy(tutar, bullet_vade, egri_p),
        }
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
        st.dataframe(
            pd.DataFrame(satirlar).set_index("Strateji").style.format("{:,.4f}"),
            width="stretch",
        )
        st.session_state["portfoyler"] = portfoyler
    except ValueError as hata:
        st.error(f"Portföy kurulamadı: {hata}")

    st.divider()
    st.markdown("**Strateji önerisi** — profilinizi seçin:")
    o1, o2, o3 = st.columns(3)
    with o1:
        beklenti = st.selectbox(
            "Faiz beklentisi",
            list(BEKLENTI_ETIKETLERI),
            format_func=BEKLENTI_ETIKETLERI.__getitem__,
        )
    with o2:
        ufuk = st.number_input("Yatırım ufku (yıl)", 0.5, 30.0, 5.0, 0.5)
    with o3:
        risk = st.selectbox(
            "Risk toleransı",
            list(RISK_ETIKETLERI),
            format_func=RISK_ETIKETLERI.__getitem__,
        )
    oneri = strateji_oner(beklenti, ufuk, risk)
    st.success(
        f"**Önerilen strateji: {oneri.strateji.upper()}** "
        f"(hedef durasyon ≈ {oneri.hedef_durasyon:.1f} yıl)\n\n{oneri.gerekce}"
    )


# ----------------------------------------------------------------------
# 4) Senaryo ve Backtest
# ----------------------------------------------------------------------
with sekme_senaryo:
    st.subheader("Faiz Senaryoları ve Strateji Backtest'i")
    if "portfoyler" not in st.session_state:
        st.info("Önce 'Portföy ve Stratejiler' sekmesinde portföyleri kurun.")
    else:
        portfoyler = st.session_state["portfoyler"]
        st.markdown("**Senaryo analizi** (anlık yeniden fiyatlama):")
        sonuclar = {isim: senaryo_analizi(p) for isim, p in portfoyler.items()}
        df_senaryo = senaryo_tablosu(sonuclar)
        st.dataframe(df_senaryo.style.format("{:+.3f}"), width="stretch")
        st.session_state["senaryo_df"] = df_senaryo

        fig, ax = plt.subplots(figsize=(11, 5))
        x = np.arange(len(df_senaryo.index))
        genislik = 0.8 / max(len(df_senaryo.columns), 1)
        for i, strateji in enumerate(df_senaryo.columns):
            ax.bar(x + i * genislik, df_senaryo[strateji].to_numpy(), genislik, label=strateji)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x + genislik * (len(df_senaryo.columns) - 1) / 2)
        ax.set_xticklabels(df_senaryo.index, rotation=20, ha="right", fontsize=8)
        ax.set_ylabel("Değer değişimi (%)")
        ax.legend()
        ax.grid(True, axis="y", alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)

        st.divider()
        st.markdown("**Backtest** (kupon reinvest + ufuk sonu yeniden fiyatlama):")
        b1, b2, b3 = st.columns(3)
        with b1:
            ufuk_bt = st.slider("Backtest ufku (yıl)", 1, 8, 3)
        with b2:
            patika_sayisi = st.slider("Vasicek patika sayısı", 50, 500, 200, 50)
        with b3:
            seed = st.number_input("Rastgelelik tohumu (seed)", 0, 10_000, 42)

        if st.button("Backtest'i çalıştır", type="primary"):
            with st.spinner("Backtest koşuluyor..."):
                egri_kaynak = dibs_ornek_egrisi().spot_egri()
                sonuc = stratejileri_backtest_et(
                    egri_kaynak,
                    ufuk_yil=float(ufuk_bt),
                    patika_sayisi=int(patika_sayisi),
                    seed=int(seed),
                )
            st.markdown("*Deterministik patikalar — yıllık getiri (%):*")
            st.dataframe(sonuc.deterministik.style.format("{:+.3f}"), width="stretch")
            st.markdown("*Vasicek simülasyonu — yıllık getiri dağılımı (%):*")
            st.dataframe(sonuc.stokastik_ozet.style.format("{:.3f}"), width="stretch")
            st.caption(f"Parametreler: {sonuc.parametreler}")

            grafik_yolu = backtest_grafigi(sonuc, cikti_klasoru=CIKTI_KLASORU)
            st.image(str(grafik_yolu))
            st.session_state["backtest_sonuc"] = sonuc


# ----------------------------------------------------------------------
# 5) Rapor
# ----------------------------------------------------------------------
with sekme_rapor:
    st.subheader("Excel Raporu")
    st.markdown(
        "Fiyatlama örneği, kurulmuş portföyler, senaryo analizi ve (varsa) "
        "backtest sonuçlarını tek Excel dosyasında toplar."
    )
    st.caption(ORNEK_VERI_UYARISI)

    if st.button("Raporu üret", type="primary"):
        ornek_tahviller = [
            Tahvil(100, 0.25, 2, 1, isim="2Y %25 kuponlu"),
            Tahvil(100, 0.22, 5, 2, isim="5Y %22 6 aylık"),
            Tahvil(100, 0.0, 10, 1, isim="10Y sıfır kuponlu"),
        ]
        fiyatlama_df = fiyatlama_tablosu(ornek_tahviller, [0.30, 0.27, 0.24])
        rapor_portfoyler = st.session_state.get("portfoyler")
        senaryo_df = st.session_state.get("senaryo_df")
        bt = st.session_state.get("backtest_sonuc")

        with st.spinner("Rapor yazılıyor..."):
            yollar = rapor_uret(
                fiyatlama=fiyatlama_df,
                portfoyler=rapor_portfoyler,
                senaryolar=senaryo_df,
                backtest_deterministik=bt.deterministik if bt else None,
                backtest_ozet=bt.stokastik_ozet if bt else None,
                dosya_adi="tahvil_raporu.xlsx",
                cikti_klasoru=CIKTI_KLASORU,
            )
        excel_yolu = yollar["excel"][0]
        st.success(
            f"Rapor üretildi: `{excel_yolu}` (+{len(yollar['csv'])} CSV). "
            "Aşağıdan indirebilirsiniz."
        )
        st.download_button(
            "Excel raporunu indir",
            data=excel_yolu.read_bytes(),
            file_name="tahvil_raporu.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        for csv_yolu in yollar["csv"]:
            st.caption(f"CSV: {csv_yolu}")
