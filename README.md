# Tahvil Değerleme ve Strateji Analizi (`bond_lab`)

![Sürüm](https://img.shields.io/badge/s%C3%BCr%C3%BCm-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Lisans](https://img.shields.io/badge/lisans-MIT-green)
![CI](https://github.com/h4nocturna/tahvil-degerleme/actions/workflows/ci.yml/badge.svg)
![Kod stili](https://img.shields.io/badge/kod%20stili-ruff%20%7C%20mypy-black)

Python ile yazılmış, **tahvil (bono) değerleme** ve **yatırım stratejisi belirleme** aracı.
Sabit kuponlu ve sıfır kuponlu tahvilleri fiyatlar; getiri, durasyon, konveksite gibi
risk ölçütlerini hesaplar; piyasa verisinden getiri eğrisi çıkarır (bootstrapping);
merdiven / barbell / bullet portföyleri kurar, faiz senaryoları altında karşılaştırır
ve yatırımcı profiline göre **Türkçe gerekçeli strateji önerisi** üretir.

Genişletme katmanıyla birlikte ayrıca: gerçek takvim tarihli **gün sayım
konvansiyonları** (ACT/365F, ACT/360, 30/360, ACT/ACT), **canlı FRED verisi**
(ABD Hazine eğrisi; internet yoksa temsili veriye düşer), **kredi spread'i /
Z-spread**, **enflasyona endeksli tahvil** (TÜFE'ye endeksli DİBS benzeri, Fisher
denklemi), **strateji backtest motoru** (deterministik patikalar + Vasicek
simülasyonu), **Excel/CSV raporlama**, **Streamlit web arayüzü** ve isteğe bağlı
**FastAPI** REST katmanı içerir.

> **Ekip:** İki kişilik ekip; public commit geçmişi şu an tek hesap
> ([h4nocturna](https://github.com/h4nocturna)) üzerinden görünür.

## İçindekiler

- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Web Arayüzü (Streamlit)](#web-arayüzü-streamlit)
- [Örnek Çıktılar](#örnek-çıktılar)
- [Proje Yapısı](#proje-yapısı)
- [Mimari](#mimari)
- [Modüller](#modüller)
- [Test ve Kod Kalitesi](#test-ve-kod-kalitesi)
- [Finansal Kavramlar (kısa sözlük)](#finansal-kavramlar-kısa-sözlük)
- [Stratejiler](#stratejiler)
- [Veri Kaynakları ve "Temsili Veri" Uyarısı](#veri-kaynakları-ve-temsili-veri-uyarısı)
- [Varsayımlar ve Sınırlar](#varsayımlar-ve-sınırlar)
- [Lisans ve Yasal Uyarı](#lisans-ve-yasal-uyarı)

## Kurulum

```bash
git clone https://github.com/h4nocturna/tahvil-degerleme.git
cd tahvil-degerleme

python -m venv .venv

# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt

# macOS / Linux
# .venv/bin/python -m pip install -r requirements.txt
```

Aşağıdaki komutlarda `python` yerine sanal ortam yorumlayıcısını kullanın
(Windows: `.venv\Scripts\python.exe`, Unix: `.venv/bin/python`).

## Kullanım

```bash
# Uçtan uca tam demo: fiyatlama, risk, eğri, stratejiler, senaryolar,
# öneri motoru, backtest özeti, Excel raporu ve output/ klasörüne PNG grafikler
python main.py

# Tek tahvil fiyatlama (%10 kuponlu, 5 yıl vadeli, %12 getiriyle)
python main.py fiyatla --kupon 0.10 --vade 5 --ytm 0.12

# 6 aylık kuponlu örnek
python main.py fiyatla --kupon 0.12 --vade 7 --ytm 0.11 --frekans 2

# Profilinize göre strateji önerisi
python main.py oner --beklenti dusecek --ufuk 5 --risk orta

# Strateji backtest'i (deterministik patikalar + Vasicek simülasyonu)
python main.py backtest --ufuk 3 --patika 200

# Excel + CSV raporu üret (output/ klasörüne)
python main.py rapor

# Streamlit web arayüzünü başlat (alternatif: main.py web)
python -m streamlit run app.py

# İsteğe bağlı REST API (Swagger: http://localhost:8000/docs)
python -m uvicorn api.main:app --reload --port 8000

# Testler
python -m pytest tests/ -v
```

## Web Arayüzü (Streamlit)

`python -m streamlit run app.py` komutu tarayıcıda Türkçe,
sekmeli bir arayüz açar (varsayılan adres `http://localhost:8501`):

1. **Tahvil Fiyatlama** — nominal/kupon/frekans/vade girin; YTM'den fiyat veya
   fiyattan YTM yönünde hesaplayın. Durasyon, konveksite, DV01 metrikleri ve
   fiyat–getiri grafiği anında güncellenir.
2. **Getiri Eğrisi** — veri kaynağı seçin (temsili DİBS, temsili ABD Hazine,
   canlı FRED veya kendi CSV'niz); spot + 1Y forward eğri ve Nelson-Siegel
   uydurması çizilir.
3. **Portföy ve Stratejiler** — merdiven/barbell/bullet portföylerini kurup
   metrik tablosunda karşılaştırın; faiz beklentisi + ufuk + risk toleransı
   seçimine göre gerekçeli Türkçe strateji önerisi alın.
4. **Senaryo ve Backtest** — paralel kayma/eğim senaryoları tablo + grafik;
   backtest motorunu (ufuk, patika sayısı, seed ayarlanabilir) çalıştırın.
5. **Rapor** — tüm sonuçları tek Excel dosyasında toplayıp indirin.

Örnek akış: önce sekme 3'te portföyleri kurun → sekme 4'te senaryo ve
backtest'i koşun → sekme 5'te raporu üretip indirin.

## Örnek Çıktılar

`main.py` tam demosu `output/` klasörüne şu dosyaları üretir:

| Dosya | İçerik |
|---|---|
| `fiyat_getiri.png` | Fiyat–getiri eğrileri; dışbükeylik (konveksite) görsel olarak izlenir. |
| `getiri_egrisi.png` | Bootstrap spot eğri, 1Y forward oranlar ve Nelson-Siegel uydurması. |
| `strateji_karsilastirma.png` | Faiz senaryoları altında merdiven/barbell/bullet değer değişimleri. |
| `nakit_akisi.png` | Portföylerin yıl bazında nakit akışı takvimleri. |
| `backtest_karsilastirma.png` | Deterministik patika getirileri + Vasicek getiri dağılımı (kutu grafiği). |
| `tahvil_raporu.xlsx` | Çok sayfalı Excel raporu (fiyatlama, portföyler, senaryo, backtest). |
| `rapor_*.csv` | Aynı tabloların tek tek CSV kopyaları (`utf-8-sig`). |

Konsol çıktısı 10 numaralı bölüme kadar Türkçe açıklamalı tablolar içerir:
fiyatlama/YTM gidiş-dönüş doğrulaması, durasyon-konveksite tahmin kalitesi,
bootstrap edilen spot/forward oranlar, strateji metrikleri, senaryo matrisi,
immünizasyon ağırlıkları, profil bazlı öneriler ve backtest özetleri.

### Kod içinden kullanım örneği

```python
from bond_lab import Tahvil, kirli_fiyat, ytm_bul, macaulay_durasyon, konveksite

tahvil = Tahvil(nominal=100, kupon_orani=0.10, vade_yil=5, frekans=1)
fiyat = kirli_fiyat(tahvil, ytm=0.12)          # 92.79...
ytm   = ytm_bul(tahvil, fiyat, temiz=False)    # 0.12 (gidiş-dönüş)
dur   = macaulay_durasyon(tahvil, 0.12)        # ~4.07 yıl
konv  = konveksite(tahvil, 0.12)               # ~20.2
```

```python
from bond_lab import GetiriEgrisi, Tahvil, merdiven_portfoy, senaryo_analizi, strateji_oner

# Par tahvil kotasyonlarından spot eğri (bootstrapping)
enstrumanlar = [(Tahvil(100, c, v, 1), 100.0)
                for v, c in {1: 0.36, 2: 0.33, 3: 0.305, 5: 0.27}.items()]
egri = GetiriEgrisi.bootstrap(enstrumanlar)

portfoy = merdiven_portfoy(1_000_000, [1, 2, 3, 5], egri)
sonuc = senaryo_analizi(portfoy)                       # ±50/100/200bp + eğim senaryoları
oneri = strateji_oner("dusecek", ufuk_yil=5, risk_toleransi="orta")
print(oneri.strateji, "-", oneri.gerekce)
```

## Proje Yapısı

```
tahvil_degerleme/
├── bond_lab/
│   ├── __init__.py        # Paket dışa aktarımları
│   ├── bond.py            # Tahvil sınıfı, nakit akışları, işlemiş faiz
│   ├── pricing.py         # YTM'den fiyat, fiyattan YTM, spot eğriden fiyat, cari getiri
│   ├── risk.py            # Macaulay/modifiye/dolar durasyon, DV01, konveksite
│   ├── yield_curve.py     # Spot eğri, bootstrapping, forward, Nelson-Siegel
│   ├── portfolio.py       # Portföy, ağırlıklı ölçütler, nakit akışı takvimi
│   ├── strategies.py      # Merdiven/barbell/bullet, senaryolar, immünizasyon, öneri
│   ├── visualization.py   # Matplotlib PNG grafikleri (Agg backend)
│   ├── conventions.py     # Gün sayım konvansiyonları (ACT/365F, ACT/360, 30/360, ACT/ACT),
│   │                      #   T+1/T+2 valör kaydırma, tarih bazlı işlemiş faiz
│   ├── market_data.py     # Canlı FRED çekimi, temsili DİBS/UST setleri, CSV yükleme
│   ├── credit.py          # Rating→spread tablosu, spread'li fiyatlama, Z-spread çözümü
│   ├── inflation.py       # Enflasyona endeksli tahvil, Fisher denklemi
│   ├── backtest.py        # Deterministik patikalar + Vasicek simülasyonu, strateji backtest'i
│   └── report.py          # Excel (çok sayfalı) + CSV raporlama
├── tests/                 # pytest testleri (çekirdek + genişletme; CI'da koşar)
├── api/                   # FastAPI REST katmanı (isteğe bağlı)
├── data/                  # Örnek veri CSV'leri (dibs_ornek.csv, ust_egri_ornek.csv)
├── docs/
│   └── MIMARI.md          # Modül mimarisi, veri akışı, tasarım kararları
├── main.py                # Türkçe demo + CLI (demo / fiyatla / oner / backtest / rapor / web)
├── app.py                 # Streamlit web arayüzü (Türkçe, 5 sekme)
├── pyproject.toml         # Proje metadata'sı + ruff/black/mypy/pytest yapılandırması
├── kalite_kontrol.ps1     # Windows: tek komutla kalite denetimi
├── kalite_kontrol.sh      # Linux/macOS: aynı kontroller (ruff/mypy/pytest + black)
├── requirements.txt
├── CHANGELOG.md           # Sürüm geçmişi
├── LICENSE                # MIT
└── output/                # PNG grafikler, Excel/CSV raporlar (üretilir, versiyonlanmaz)
```

## Mimari

Paket katmanlı tasarlanmıştır: en altta saf veri modeli (`bond`), üstünde durum
tutmayan hesaplama fonksiyonları (`pricing`, `risk`, `yield_curve`), onların
üzerinde birleşik yapılar (`portfolio`, `strategies`, `backtest`) ve en üstte
sunum katmanı (`visualization`, `report`, `main.py`, `app.py`). Bağımlılık yönü
her zaman yukarıdan aşağıyadır. Ayrıntılı modül şeması, veri akışı ve tasarım
kararları için bkz. **[docs/MIMARI.md](docs/MIMARI.md)**.

## Modüller

| Modül | İçerik |
|---|---|
| `bond.py` | `Tahvil` veri sınıfı: nominal, kupon oranı, frekans (1/2/4/12), kesirli vade desteği, nakit akışı üretimi, işlemiş faiz. Sıfır kuponlu tahvil `kupon_orani=0` ile tanımlanır. |
| `pricing.py` | `kirli_fiyat` / `temiz_fiyat` (YTM'den), `ytm_bul` (Newton-Raphson + garantili bisection yedeği), `spot_egriden_fiyat`, `cari_getiri`. |
| `risk.py` | `macaulay_durasyon`, `modifiye_durasyon`, `dolar_durasyon`, `dv01`, `konveksite`; `fiyat_degisim_karsilastir` ile durasyon(+konveksite) tahmini vs gerçek yeniden fiyatlama. |
| `yield_curve.py` | `GetiriEgrisi` (doğrusal/kübik interpolasyon, iskonto faktörü, forward oran), `GetiriEgrisi.bootstrap` (kuponlu tahvillerden spot eğri), `nelson_siegel_uydur`. |
| `portfolio.py` | `Pozisyon` ve `Portfoy`: piyasa değeri, ağırlıklı durasyon/konveksite/getiri, birleşik nakit akışı takvimi, senaryo değerlemesi. |
| `strategies.py` | `merdiven_portfoy`, `barbell_portfoy`, `bullet_portfoy`, `immunizasyon_portfoy`, `standart_senaryolar`, `senaryo_analizi`, `strateji_oner` (Türkçe gerekçeli öneri). |
| `visualization.py` | Fiyat-getiri eğrisi, spot/forward/Nelson-Siegel eğrisi, senaryo bazlı strateji karşılaştırma bar grafiği, portföy nakit akışı zaman çizelgesi. |
| `conventions.py` | `yil_kesri` (ACT/365F, ACT/360, 30/360 US, basitleştirilmiş ACT/ACT ISDA), `valor_tarihi` (T+1/T+2, hafta sonu atlama), `kupon_tarihleri` (vadeden geriye takvim), `islemis_faiz_tarihli` (gerçek tarihlerle işlemiş faiz). |
| `market_data.py` | `fred_hazine_egrisi` (FRED public CSV, timeout + sessiz yedek), `dibs_ornek_seti` / `ust_ornek_egrisi` (temsili veri, etiketli), `ornek_csvleri_yaz`, `tahvilleri_csvden_yukle`, `egriyi_csvden_yukle`, `kotasyonlardan_enstrumanlar` (bootstrap köprüsü). |
| `credit.py` | `RATING_SPREAD_BP` (AAA…B temsili spread tablosu), `spreadli_fiyat` (eğri + sabit spread), `z_spread_bul` (fiyattan Z-spread, brentq), `spread_duyarliligi` (spread DV01). |
| `inflation.py` | `EndeksliTahvil` (endeks oranlı nakit akışları, deflasyon taban koruması), `fisher_nominal` / `fisher_reel` (tam ve yaklaşık Fisher), `endeks_orani`, `basit_degerleme`. |
| `backtest.py` | `deterministik_patikalar` (kademeli artış/düşüş, sabit, ani şok), `vasicek_patikalari` (seed'li stokastik simülasyon), `portfoy_backtest` (kupon reinvest + ufuk sonu yeniden fiyatlama), `stratejileri_backtest_et`, `backtest_grafigi`. |
| `report.py` | `fiyatlama_tablosu`, `portfoy_tablosu`, `senaryo_tablosu`, `excele_yaz` (çok sayfalı, Türkçe başlıklar), `csvlere_yaz` (utf-8-sig), `rapor_uret` (dosya varlığı doğrulamalı). |

## Test ve Kod Kalitesi

Tüm araç yapılandırmaları `pyproject.toml` içindedir (satır uzunluğu 100,
ruff kural setleri E/F/W/I/N/UP/B, mypy `check_untyped_defs`). Tek komutla
tam denetim:

> **Not:** `kalite_kontrol.ps1` Windows'a özeldir. Linux/macOS için
> `./kalite_kontrol.sh` kullanın. CI (GitHub Actions) Linux'ta aynı kontrolleri
> (`pytest` + `ruff` + `mypy`) çalıştırır — üstteki CI rozetine bakın.

```powershell
# Windows — denetim / düzeltme
.\kalite_kontrol.ps1
.\kalite_kontrol.ps1 -Duzelt
```

```bash
# Linux / macOS — denetim / düzeltme
chmod +x kalite_kontrol.sh   # bir kez
./kalite_kontrol.sh
./kalite_kontrol.sh --duzelt
```

Araçları tek tek çalıştırmak için:

```bash
python -m pytest tests/ -v     # birim testleri
python -m ruff check .         # lint
python -m mypy bond_lab        # statik tip denetimi
```

Testler kapalı form finansal sonuçlarla karşılaştırır (par tahvil = nominal,
sıfır kuponlu durasyon = vade, YTM/Z-spread gidiş-dönüş, sonlu fark ile
durasyon/konveksite doğrulaması) ve FRED çağrısını ağa çıkmadan mock'lar.

## Finansal Kavramlar (kısa sözlük)

- **YTM (Vadeye Kadar Getiri):** Tahvilin tüm nakit akışlarının bugünkü değerini
  piyasa fiyatına eşitleyen yıllık iskonto oranı. Dönemsel getiri = YTM / frekans,
  dönem sayısı = vade × frekans kuralıyla bileşiklenir.
- **Temiz / Kirli Fiyat:** Kirli fiyat ödenecek gerçek tutardır; temiz fiyat = kirli
  fiyat − işlemiş (birikmiş) kupon faizi. Piyasada kotasyon genellikle temiz fiyattır.
- **Cari Getiri:** Yıllık kupon tutarı / temiz fiyat; basit bir taşıma göstergesi.
- **Macaulay Durasyonu:** Nakit akışlarının bugünkü değer ağırlıklı ortalama vadesi (yıl).
- **Modifiye Durasyon:** Getirideki 1 puanlık değişime karşı fiyatın yüzde duyarlılığı;
  `D_mod = D_mac / (1 + YTM/frekans)`.
- **DV01 / PVBP:** 1 baz puanlık (0.01 puan) getiri değişiminin fiyata parasal etkisi.
- **Konveksite:** Fiyat-getiri eğrisinin dışbükeyliği; durasyon tahminini iyileştirir.
  Büyük faiz şoklarında `ΔP ≈ P·(−D_mod·Δy + ½·C·Δy²)` belirgin daha isabetlidir.
- **Spot Oran / Getiri Eğrisi:** Sıfır kuponlu (tek ödemeli) getirilerin vadeye göre
  eğrisi. Kuponlu tahvil fiyatlarından **bootstrapping** ile ardışık çözülür.
- **Forward Oran:** Eğrinin ima ettiği gelecekteki dönem faizi:
  `(1+z₂)^t₂ = (1+z₁)^t₁ · (1+f)^(t₂−t₁)`.
- **Nelson-Siegel:** Getiri eğrisini 4 parametreyle (seviye, eğim, kamburluk, ölçek)
  pürüzsüz biçimde temsil eden klasik parametrik model.

## Stratejiler

- **Merdiven (Ladder):** Tutar eşit dilimlerle farklı vadelere yayılır; vadesi gelen
  anapara en uzun basamağa yeniden yatırılır. Yeniden yatırım riskini dengeler,
  düzenli nakit akışı sağlar; faiz tahmini gerektirmez.
- **Barbell (Halter):** Yalnızca kısa ve uzun uçlara yatırım yapılır; orta vadeler boş.
  Aynı durasyonlu bullet'a göre konveksitesi yüksektir; büyük faiz hareketlerinde ve
  yataylaşma senaryolarında avantajlıdır.
- **Bullet (Mermi):** Tüm tutar tek hedef vadede toplanır. Nakit ihtiyacının zamanı
  kesin olduğunda idealdir; hedefe kilitlenir ama esnekliği düşüktür.
- **İmmünizasyon:** Portföyün Macaulay durasyonu yatırım ufkuna eşitlenir; küçük
  paralel faiz oynamalarında fiyat riski ile yeniden yatırım riski birbirini dengeler.
- **Öneri motoru (`strateji_oner`):** Faiz beklentisi (`yukselecek/dusecek/sabit`),
  yatırım ufku ve risk toleransına (`dusuk/orta/yuksek`) göre yukarıdaki
  stratejilerden birini hedef durasyonla birlikte önerir ve gerekçesini Türkçe açıklar.

## Veri Kaynakları ve "Temsili Veri" Uyarısı

- **Canlı FRED (ABD Hazine):** `market_data.fred_hazine_egrisi` FRED'in halka
  açık CSV uç noktasından (DGS3MO, DGS6MO, DGS1, DGS2, DGS5, DGS10, DGS30)
  son gözlemleri çeker. İstek zaman aşımına uğrar veya internet yoksa
  **sessizce gömülü temsili veriye düşülür** (uygulama kesintiye uğramaz).
- **Temsili/örnek veriler:** Türkiye DİBS seti ve ABD Hazine örnek eğrisi
  GERÇEK PİYASA KOTASYONU DEĞİLDİR; kodda ve CSV başlıklarında açıkça
  "temsili/örnek veri" olarak etiketlenmiştir (referans tarihi: 2026-06-30
  seviyelerine göre kurgu). Kredi spread tablosu da temsilidir.
- **Kendi veriniz:** `data/dibs_ornek.csv` (sütunlar: `isim, vade_yil,
  kupon_orani, frekans, ytm, temiz_fiyat`) ve `data/ust_egri_ornek.csv`
  (sütunlar: `vade_yil, oran`) ile aynı şemada CSV hazırlayıp
  `tahvilleri_csvden_yukle` / `egriyi_csvden_yukle` ile veya web arayüzünün
  "CSV yükle" seçeneğiyle kullanabilirsiniz.

## Varsayımlar ve Sınırlar

- Oranlar yıllık **bileşik** getiridir; iskonto `(1 + y/f)^(f·t)` kuralıyla yapılır.
- `Tahvil` sınıfında kesirli vadede işlemiş faiz, dönem kesri üzerinden doğrusal
  hesaplanır; gerçek takvim tarihleriyle gün sayım konvansiyonlu hesap için
  `conventions.py` (ACT/365F, ACT/360, 30/360 US, basitleştirilmiş ACT/ACT) kullanılır.
- Kredi katmanı sabit (deterministik) spread varsayar; temerrüt olasılığı /
  kurtarma oranı modellenmez. Opsiyonlu (callable) tahviller kapsam dışıdır.
- Backtest basitleştirilmiş yeniden fiyatlama kullanır: paralel kayma patikaları,
  kuponların kısa vadeli oranla reinvest'i, ufuk sonunda `başlangıç YTM + kayma`
  ile değerleme (roll-down ihmal edilir). Vasicek parametreleri örnek amaçlıdır.
- Enflasyona endeksli değerleme tek endeks katsayısı kullanır; endeksleme
  gecikmesi (lag) ihmal edilir.

## Lisans ve Yasal Uyarı

Bu proje [MIT lisansı](LICENSE) ile lisanslanmıştır. Sürüm geçmişi için
bkz. [CHANGELOG.md](CHANGELOG.md).

> **Yasal uyarı:** Bu yazılım yalnızca eğitim ve analiz amaçlıdır;
> **yatırım tavsiyesi değildir**. Üretilen fiyat, getiri, senaryo ve backtest
> sonuçları basitleştirilmiş modellere ve kısmen temsili verilere dayanır;
> gerçek işlem kararları için lisanslı bir yatırım danışmanına başvurun.
> Yazarlar, bu yazılımın kullanımından doğabilecek zararlardan sorumlu tutulamaz.
