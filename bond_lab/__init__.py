"""bond_lab — Tahvil değerleme ve yatırım stratejisi analiz paketi.

Çekirdek modüller:
    bond          : Tahvil tanımı ve nakit akışı üretimi
    pricing       : Fiyatlama (YTM'den fiyat, fiyattan YTM, spot eğriden fiyat)
    risk          : Durasyon, konveksite, DV01 gibi faiz riski ölçütleri
    yield_curve   : Spot eğri, bootstrapping, forward oranlar, Nelson-Siegel
    portfolio     : Tahvil portföyü ve ağırlıklı ölçütler
    strategies    : Merdiven/halter/mermi stratejileri, senaryo analizi, öneri motoru
    visualization : Matplotlib grafikleri (PNG çıktı; ayrıca import edilir)

Genişletme modülleri (alt modül olarak import edilir, örn.
``from bond_lab.credit import z_spread_bul``):
    conventions   : Gün sayım konvansiyonları, valör kaydırma, tarihli işlemiş faiz
    market_data   : Canlı FRED verisi, temsili DİBS/UST setleri, CSV yükleme
    credit        : Rating→spread, spread'li fiyatlama, Z-spread çözümü
    inflation     : Enflasyona endeksli tahvil, Fisher denklemi
    backtest      : Deterministik + Vasicek faiz patikalarıyla strateji backtest'i
    report        : Excel (çok sayfalı) ve CSV raporlama
"""

from bond_lab.bond import NakitAkisi, Tahvil
from bond_lab.portfolio import Portfoy, Pozisyon
from bond_lab.pricing import (
    cari_getiri,
    kirli_fiyat,
    spot_egriden_fiyat,
    temiz_fiyat,
    ytm_bul,
)
from bond_lab.risk import (
    dolar_durasyon,
    dv01,
    fiyat_degisim_karsilastir,
    fiyat_degisim_tahmini,
    konveksite,
    macaulay_durasyon,
    modifiye_durasyon,
)
from bond_lab.strategies import (
    StratejiOnerisi,
    barbell_portfoy,
    bullet_portfoy,
    immunizasyon_portfoy,
    merdiven_portfoy,
    senaryo_analizi,
    standart_senaryolar,
    strateji_oner,
)
from bond_lab.yield_curve import (
    GetiriEgrisi,
    NelsonSiegelSonuc,
    nelson_siegel_orani,
    nelson_siegel_uydur,
)

__version__ = "1.0.0"

__all__ = [
    "Tahvil",
    "NakitAkisi",
    "kirli_fiyat",
    "temiz_fiyat",
    "ytm_bul",
    "cari_getiri",
    "spot_egriden_fiyat",
    "macaulay_durasyon",
    "modifiye_durasyon",
    "dolar_durasyon",
    "dv01",
    "konveksite",
    "fiyat_degisim_tahmini",
    "fiyat_degisim_karsilastir",
    "GetiriEgrisi",
    "NelsonSiegelSonuc",
    "nelson_siegel_orani",
    "nelson_siegel_uydur",
    "Portfoy",
    "Pozisyon",
    "merdiven_portfoy",
    "bullet_portfoy",
    "barbell_portfoy",
    "immunizasyon_portfoy",
    "standart_senaryolar",
    "senaryo_analizi",
    "strateji_oner",
    "StratejiOnerisi",
]
