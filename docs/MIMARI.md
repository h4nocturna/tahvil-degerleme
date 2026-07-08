# Mimari Dokümantasyonu

Bu belge, **bond-lab** (tahvil değerleme ve strateji analizi) projesinin modül
mimarisini, veri akışını ve temel tasarım kararlarını açıklar.

## 1. Genel Bakış

Proje, katmanlı bir mimariyle tasarlanmıştır: en altta saf veri modeli
(`bond`), üstünde durum tutmayan hesaplama fonksiyonları (`pricing`, `risk`,
`yield_curve`), onların üzerinde birleşik yapılar (`portfolio`, `strategies`)
ve en üstte sunum katmanı (`visualization`, `main.py` CLI/demo, `app.py`
Streamlit arayüzü) yer alır.

```
┌──────────────────────────────────────────────────────────────┐
│  Sunum: main.py (CLI/demo) · app.py (Streamlit) · report.py  │
├──────────────────────────────────────────────────────────────┤
│  Analiz: strategies · portfolio · backtest · visualization   │
├──────────────────────────────────────────────────────────────┤
│  Hesaplama: pricing · risk · yield_curve · credit · inflation│
├──────────────────────────────────────────────────────────────┤
│  Temel: bond (veri modeli) · conventions · market_data       │
└──────────────────────────────────────────────────────────────┘
```

Bağımlılık yönü her zaman yukarıdan aşağıyadır; alt katman modülleri üst
katmanları asla import etmez. `pricing` ↔ `yield_curve` arasındaki potansiyel
döngü, `pricing` tarafında yalnızca `TYPE_CHECKING` bloğunda import yapılarak
kırılmıştır.

## 2. Modüller

### 2.1 Çekirdek paket: `bond_lab`

| Modül | Sorumluluk |
| --- | --- |
| `bond.py` | `Tahvil` veri sınıfı (frozen dataclass): nominal, kupon, vade, frekans; nakit akışı üretimi, işlemiş faiz. |
| `pricing.py` | YTM'den kirli/temiz fiyat, fiyattan YTM (Newton-Raphson + bisection yedeği), spot eğriden fiyat, cari getiri. |
| `risk.py` | Macaulay/modifiye/dolar durasyon, DV01, konveksite, durasyon+konveksite ile fiyat değişim tahmini. |
| `yield_curve.py` | `GetiriEgrisi` (spot eğri; doğrusal/kübik interpolasyon, iskonto faktörü, forward oran), bootstrap, Nelson-Siegel uydurma. |
| `portfolio.py` | `Pozisyon` ve `Portfoy`: piyasa değeri ağırlıklı durasyon/konveksite/getiri, birleşik nakit akışı takvimi, senaryo değerlemesi. |
| `strategies.py` | Merdiven / barbell / bullet portföy kurucuları, immünizasyon, standart faiz senaryoları, senaryo analizi, Türkçe gerekçeli strateji öneri motoru. |
| `visualization.py` | Matplotlib (Agg backend) ile PNG grafik üretimi: fiyat–getiri, getiri eğrisi, strateji karşılaştırma, nakit akışı takvimi. |

### 2.2 Genişletme modülleri

| Modül | Sorumluluk |
| --- | --- |
| `conventions.py` | Gün sayım kuralları (ACT/365, ACT/360, 30/360) ve yıl kesri hesabı. |
| `market_data.py` | Örnek/CSV piyasa verisi yükleme (`data/` klasörü ile birlikte çalışır). |
| `credit.py` | Kredi marjı (spread) analizi ve kredi riskli fiyatlama. |
| `inflation.py` | Enflasyona endeksli tahvil hesaplamaları. |
| `backtest.py` | Strateji geri testi (tarihsel getiri simülasyonu). |
| `report.py` | Excel/metin rapor üretimi. |

### 2.3 Uygulama girişleri

* **`main.py`** — Türkçe uçtan uca demo ve `argparse` tabanlı CLI
  (`demo`, `fiyatla`, `oner` alt komutları). Çıktı grafikleri `output/`
  klasörüne yazılır.
* **`app.py`** — Streamlit web arayüzü; interaktif fiyatlama ve strateji
  karşılaştırması.

## 3. Veri Akışı

Tipik değerleme akışı:

```
Piyasa kotasyonları (vade, fiyat/par getiri)
        │  GetiriEgrisi.bootstrap()
        ▼
Spot getiri eğrisi (GetiriEgrisi)
        │  spot_egriden_fiyat() / strategies kurucuları
        ▼
Tahvil(ler) → Pozisyon(lar) → Portfoy
        │  senaryo_analizi(), risk ölçütleri
        ▼
Sonuç sözlükleri / DataFrame'ler
        │  visualization / report / app
        ▼
PNG grafikler · Excel raporlar · Streamlit arayüzü
```

* `Tahvil.nakit_akislari()` tüm hesaplamaların ortak temelidir: her modül
  fiyat/risk hesabını bu `(zaman_yil, tutar)` listesi üzerinden yapar.
* Fiyatlama fonksiyonları durum tutmaz (pure function); aynı girdiye her zaman
  aynı çıktıyı verir. Bu, test edilebilirliği ve paralel kullanımı kolaylaştırır.

## 4. Tasarım Kararları

1. **Türkçe genel API.** Hedef kitle Türkçe konuşan kullanıcılar olduğundan
   sınıf/fonksiyon adları, docstring'ler ve hata mesajları Türkçedir
   (`kirli_fiyat`, `macaulay_durasyon`, `GetiriEgrisi` …). ASCII güvenliği
   için tanımlayıcılarda Türkçe özel karakter kullanılmaz (ı→i, ö→o …).

2. **Zaman ekseni: yıl cinsinden kesirli vade.** Tarih aritmetiği yerine
   `vade_yil: float` tutulur; tarih girdisi `Tahvil.tarihlerden` ile
   ACT/365 üzerinden yıla çevrilir. Bu, çekirdeği takvim kurallarından
   bağımsız ve test edilebilir tutar; hassas gün sayım kuralları
   `conventions.py` genişletmesine aittir.

3. **İskonto kuralı tek ve tutarlı.** Yıllık YTM `y`, frekans `f` için akış
   `CF/(1+y/f)^(f·t)` ile indirgenir; spot eğride yıllık bileşik
   `DF(t)=(1+z)^(-t)` kullanılır. Kesirli dönem üsleri desteklenir, böylece
   kupon günleri arasında da süreklilik korunur.

4. **Sağlam kök bulma.** `ytm_bul` önce hızlı Newton-Raphson dener; türev
   sıfıra yaklaşır veya iterasyon tanım bölgesinden çıkarsa monotonluktan
   yararlanan garantili bisection'a düşer. Bootstrap'ta `scipy.brentq`
   kullanılır.

5. **Dondurulmuş (frozen) veri sınıfları.** `Tahvil`, `Pozisyon`,
   `NelsonSiegelSonuc`, `StratejiOnerisi` immutable'dır; doğrulama
   `__post_init__` içinde yapılır ve geçersiz nesne hiç yaratılamaz.

6. **Görselleştirme yan etkisiz ve headless.** Matplotlib Agg backend ile
   pencere açılmaz; fonksiyonlar dosya yolu döndürür. CI/sunucu ortamlarında
   sorunsuz çalışır.

7. **Doğrulama sınırda, çekirdekte değil.** Kullanıcıya bakan kurucular ve
   genel API fonksiyonları Türkçe mesajlı `ValueError` fırlatır; iç yardımcı
   fonksiyonlar girdilerine güvenir (savunmacı kod tekrarı yoktur).

## 5. Test Stratejisi

* `tests/` altında modül başına test dosyası bulunur; `conftest.py` proje
  kökünü `sys.path`'e ekleyerek kurulumsuz `import bond_lab` sağlar.
* Finansal doğruluk testleri kapalı form sonuçlarla karşılaştırır
  (ör. par tahvilin fiyatı nominale eşittir; sıfır kuponlu tahvilin Macaulay
  durasyonu vadesine eşittir; YTM gidiş-dönüş tutarlılığı).
* Kalite araçları: `ruff` (lint), `black` (format), `mypy` (tip), `pytest`
  (birim testleri). Tümü `kalite_kontrol.ps1` ile tek komutta koşar;
  yapılandırmalar `pyproject.toml` içindedir.

## 6. Sınırlamalar

* Takvim/iş günü kuralları basitleştirilmiştir (ACT/365 varsayılanı);
  tatil takvimi ve iş günü kaydırma uygulanmaz.
* Vergi, komisyon ve likidite etkileri modellenmez.
* Kredi riski modülü sabit marj yaklaşımıdır; temerrüt olasılığı modeli içermez.
* Bu yazılım eğitim/analiz amaçlıdır; **yatırım tavsiyesi değildir**.
