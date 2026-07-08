# Değişiklik Günlüğü

Bu projedeki kayda değer değişiklikler bu dosyada belgelenir.
Biçim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) standardını,
sürümleme [Semantik Sürümleme](https://semver.org/lang/tr/) kurallarını izler.

## [1.0.0] - 2026-07-08

### Eklendi

- `bond_lab` çekirdek paketi:
  - `Tahvil` veri modeli, nakit akışı üretimi, işlemiş faiz (`bond`)
  - YTM'den fiyat / fiyattan YTM (Newton-Raphson + bisection), spot eğriden
    fiyatlama, cari getiri (`pricing`)
  - Macaulay/modifiye/dolar durasyon, DV01, konveksite, fiyat değişim
    tahmini (`risk`)
  - Spot eğri, bootstrap, forward oranlar, Nelson-Siegel uydurma (`yield_curve`)
  - Portföy ve piyasa değeri ağırlıklı ölçütler (`portfolio`)
  - Merdiven / barbell / bullet kurucuları, immünizasyon, senaryo analizi,
    Türkçe strateji öneri motoru (`strategies`)
  - PNG grafik üretimi (`visualization`)
- Genişletme modülleri: gün sayım kuralları (`conventions`), piyasa verisi
  (`market_data`), kredi marjı (`credit`), enflasyona endeksli tahvil
  (`inflation`), strateji geri testi (`backtest`), rapor üretimi (`report`)
- `main.py` Türkçe uçtan uca demo ve CLI (`demo`, `fiyatla`, `oner`)
- `app.py` Streamlit web arayüzü
- Kapsamlı birim test paketi (`tests/`)
- Proje altyapısı: `pyproject.toml` (ruff/black/mypy/pytest yapılandırması),
  `kalite_kontrol.ps1`, MIT lisansı, mimari dokümantasyonu (`docs/MIMARI.md`)
