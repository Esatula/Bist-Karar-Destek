# BIST Karar Destek

BIST hisselerini incelemek için hazırlanmış, Streamlit tabanlı bir analiz uygulaması. Teknik göstergeleri, TradingView özetini ve haber puanlarını bir araya getirerek tarama sonuçları sunar. Hisse detayları, sanal portföy takibi ve geçmiş veriler üzerinde simülasyon araçları da içerir.

Uygulama aracı kurum hesabına bağlanmaz ve emir göndermez. Üretilen puanlar ve sinyaller analiz amaçlıdır; yatırım tavsiyesi değildir. Kullanılan piyasa ve haber verileri dış servislerden gelir, gecikmeli veya eksik olabilir.

## Özellikler

- BIST-30 ve BIST-100 hisselerini tarama
- RSI, MACD, hareketli ortalamalar ve diğer teknik göstergeleri hesaplama
- Teknik, TradingView ve haber verilerini birleştirerek sinyal puanı üretme
- Hisse grafikleri ve detay ekranları
- Sanal portföy takibi
- Geçmiş verilerle strateji simülasyonu
- Günlük tarama betiğiyle CSV sonuçları oluşturma

## Gereksinimler

- Python 3.11 veya üzeri
- Piyasa ve haber verilerini almak için internet bağlantısı

## Kurulum

Komutları depo kökünde çalıştırın:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS veya Linux:

```bash
source .venv/bin/activate
```

Bağımlılıkları kurun:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

İsteğe bağlı geliştirme bağımlılıklarıyla kurulumu da kullanabilirsiniz:

```bash
pip install -e ".[dev]"
```

## Yapılandırma

Kişisel ayar dosyanızı örnekten oluşturun:

```powershell
Copy-Item config/settings.example.yaml config/settings.yaml
```

macOS veya Linux:

```bash
cp config/settings.example.yaml config/settings.yaml
```

Takip listesi, sinyal eşikleri, risk değerleri ve veri yolları `config/settings.yaml` içinden düzenlenebilir. İsteğe bağlı API anahtarları için `.env.example` dosyasını `.env` adıyla kopyalayın ve kullanacağınız anahtarı ekleyin. `.env` ve kişisel ayar dosyası Git'e dahil edilmez.

## Çalıştırma

Arayüzü başlatın:

```bash
streamlit run ui/dashboard.py
```

Günlük tarama betiği varsayılan olarak BIST-100 evrenini tarar:

```bash
python scripts/daily_scan.py
```

BIST-30 taraması veya önbellek güncelliği kontrolünü atlamak için:

```bash
python scripts/daily_scan.py --tier bist30
python scripts/daily_scan.py --force
```

Tarama çıktıları `data/scan_results/` altında oluşturulur. İlk tarama sırasında fiyat verileri dış kaynaktan indirilebilir.

## Testler

```bash
pytest
```

## Proje yapısı

```text
backtest/       Geçmiş verilerle simülasyon
config/         Örnek ayarlar ve BIST hisse evreni
data/           Veri erişim kodu; indirilen fiyatlar ve önbellek yerel kalır
indicators/     Teknik gösterge hesaplamaları
news/           Haber ve TradingView bağlantıları
portfolio/      Sanal portföy ve yerel veritabanı
signals/        Sinyal puanlama motoru
scripts/        Komut satırı tarama araçları
tests/          Otomatik testler
ui/             Streamlit arayüzü
```

Fiyat dosyaları, yerel veritabanları, sanal ortamlar, loglar ve kişisel ayarlar repoya gönderilmemelidir.
