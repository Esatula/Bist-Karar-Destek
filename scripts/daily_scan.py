"""
scripts/daily_scan.py
---------------------
Günlük otomatik BIST-100 tarama betiği.
Windows Task Scheduler veya elle çalıştırılabilir.

Yapılanlar:
    1. BIST-100 fiyat verilerini günceller
    2. TradingView + Teknik + Haber sinyallerini hesaplar
    3. Sonuçları data/scan_results/ klasörüne CSV olarak kaydeder
    4. Konsola AL/SAT özetini yazar

Kullanım:
    python scripts/daily_scan.py
    python scripts/daily_scan.py --tier bist30
    python scripts/daily_scan.py --force     # Stale kontrolünü atla
"""

import sys
import os
import time
import logging
from datetime import datetime
from pathlib import Path

# Proje kökünü path'e ekle
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import yaml
import pandas as pd

# ---------------------------------------------------------------------------
# Loglama
# ---------------------------------------------------------------------------
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f"scan_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    start_time = time.time()

    # Args
    tier  = "bist100"
    force = "--force" in sys.argv
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith("--tier"):
            tier = arg.split("=")[-1] if "=" in arg else sys.argv[i + 1]

    logger.info("=" * 65)
    logger.info("  BIST Günlük Tarama Başlıyor — %s", datetime.now().strftime("%d.%m.%Y %H:%M"))
    logger.info("  Evren: %s | Force: %s", tier.upper(), force)
    logger.info("=" * 65)

    # Config yükle
    cfg_path = project_root / "bist_bot" / "config" / "settings.yaml"
    if not cfg_path.exists():
        cfg_path = project_root / "bist_bot" / "config" / "settings.example.yaml"

    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    price_folder = str(project_root / "bist_bot" / cfg["storage"]["price_data_folder"])
    db_path      = str(project_root / "bist_bot" / cfg["storage"]["news_db_path"])
    weights      = cfg.get("signal_weights", {"technical": 0.5, "tradingview": 0.2, "news": 0.3})
    thresholds   = cfg.get("signal_thresholds", {"buy": 70, "sell": 30})
    tv_interval  = cfg.get("tradingview", {}).get("interval", "1d")

    os.chdir(project_root / "bist_bot")

    # Tarama
    from data.universe_scanner import quick_scan

    logger.info("Tarama başlıyor...")
    t0 = time.time()
    df = quick_scan(
        tier=tier,
        price_folder=price_folder,
        db_path=db_path,
        tv_interval=tv_interval,
        weights=weights,
        buy_threshold=thresholds.get("buy", 70),
        sell_threshold=thresholds.get("sell", 30),
        auto_update=True,
        max_age_hours=0 if force else 4,
    )
    t1 = time.time()

    if df.empty:
        logger.error("Tarama sonucu boş! Veri dosyalarını kontrol edin.")
        sys.exit(1)

    # Özet
    al_list  = df[df["recommendation"] == "AL"]
    sat_list = df[df["recommendation"] == "SAT"]

    logger.info("")
    logger.info("─" * 65)
    logger.info("TARAMA ÖZETI — %s", datetime.now().strftime("%d.%m.%Y %H:%M"))
    logger.info("  Toplam: %d hisse | Süre: %.1fs", len(df), t1 - t0)
    logger.info("  🟢 AL: %d  ⚪ BEKLE: %d  🔴 SAT: %d",
                len(al_list),
                len(df[df["recommendation"] == "BEKLE"]),
                len(sat_list))
    logger.info("─" * 65)

    if not al_list.empty:
        logger.info("TOP AL HİSSELER:")
        for _, row in al_list.head(10).iterrows():
            logger.info("  %-8s Skor:%.0f  TV:%-12s RSI:%.0f  ₺%.2f",
                        row["symbol"], row["final_score"],
                        row["tv_rec"], row["rsi"], row["last_price"])

    if not sat_list.empty:
        logger.info("TOP SAT HİSSELER:")
        for _, row in sat_list.head(5).iterrows():
            logger.info("  %-8s Skor:%.0f  TV:%-12s RSI:%.0f  ₺%.2f",
                        row["symbol"], row["final_score"],
                        row["tv_rec"], row["rsi"], row["last_price"])

    # CSV kaydet
    results_dir = project_root / "bist_bot" / "data" / "scan_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    ts  = datetime.now().strftime("%Y%m%d_%H%M")
    csv = results_dir / f"scan_{ts}.csv"
    df.to_csv(csv, index=False, encoding="utf-8")
    logger.info("CSV kaydedildi: %s", csv)

    # En güncel sonuçları 'latest.csv' olarak da kaydet
    latest = results_dir / "latest.csv"
    df.to_csv(latest, index=False, encoding="utf-8")

    total_time = time.time() - start_time
    logger.info("=" * 65)
    logger.info("  Tarama tamamlandı. Toplam süre: %.1f saniye", total_time)
    logger.info("=" * 65)


if __name__ == "__main__":
    main()
