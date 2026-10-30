"""
news/tv_signals.py
------------------
TradingView teknik analiz sinyallerini çeken modül.

tradingview-ta kütüphanesi (pip install tradingview-ta) kullanılarak
BIST hisseleri için TradingView'ın toplulaştırılmış teknik sinyal
özeti (AL/SAT/NÖTR + indikatör sayıları) çekilir.

API anahtarı gerektirmez; ücretsizdir.

Dönen tv_score değeri 0-100 arasında normalize edilmiş bir
"AL eğilimi" puanıdır:
    100 → Tüm indikatörler AL diyor (STRONG_BUY)
      0 → Tüm indikatörler SAT diyor (STRONG_SELL)
     50 → Tam nötr

Kullanım:
    python -m news.tv_signals
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Interval sabitleri — tradingview_ta.Interval'ı tekrar expose et
try:
    from tradingview_ta import TA_Handler, Interval
    _TV_AVAILABLE = True
except ImportError:
    _TV_AVAILABLE = False
    logger.warning(
        "tradingview-ta paketi bulunamadi. "
        "pip install tradingview-ta komutuyla kurun."
    )

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# TradingView'da BIST hisselerine ait screener ve exchange bilgileri
_SCREENER  = "turkey"
_EXCHANGE  = "BIST"

# tradingview_ta Interval sabitleri → okunabilir string eşlemesi
_INTERVAL_MAP: dict[str, str] = {
    "1m":  "INTERVAL_1_MINUTE",
    "5m":  "INTERVAL_5_MINUTES",
    "15m": "INTERVAL_15_MINUTES",
    "1h":  "INTERVAL_1_HOUR",
    "4h":  "INTERVAL_4_HOURS",
    "1d":  "INTERVAL_1_DAY",
    "1W":  "INTERVAL_1_WEEK",
    "1M":  "INTERVAL_1_MONTH",
}

_DELAY_BETWEEN_REQUESTS = 0.3   # Saniye — sunucuya nazik ol

# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------

def _recommendation_to_str(rec: str) -> str:
    """
    TradingView öneri string'ini okunabilir Türkçeye çevirir.
    'STRONG_BUY' → 'GÜÇLÜ AL' vb.
    """
    mapping = {
        "STRONG_BUY":  "GÜÇLÜ AL",
        "BUY":         "AL",
        "NEUTRAL":     "NÖTR",
        "SELL":        "SAT",
        "STRONG_SELL": "GÜÇLÜ SAT",
    }
    return mapping.get(rec.upper(), rec)


def _compute_tv_score(buy: int, sell: int, neutral: int) -> float:
    """
    AL/SAT/NÖTR indikatör sayılarından 0-100 normalize skor üretir.

    Formül:
        score = (buy / total) * 100
    Tüm indikatörler AL  → 100
    Tüm indikatörler SAT →   0
    Tam nötr (eşit)      →  50

    Args:
        buy:     AL diyen indikatör sayısı
        sell:    SAT diyen indikatör sayısı
        neutral: NÖTR indikatör sayısı

    Returns:
        float: 0-100 arası skor
    """
    total = buy + sell + neutral
    if total == 0:
        return 50.0
    return round((buy / total) * 100, 1)


def _get_interval(interval_str: str) -> "Interval":
    """
    String interval → tradingview_ta.Interval enum dönüşümü.
    Bilinmeyen değer için 1d (günlük) kullanılır.
    """
    attr_name = _INTERVAL_MAP.get(interval_str, "INTERVAL_1_DAY")
    return getattr(Interval, attr_name, Interval.INTERVAL_1_DAY)


# ---------------------------------------------------------------------------
# Ana sinyal çekme fonksiyonu
# ---------------------------------------------------------------------------

def fetch_tv_signal(
    symbol: str,
    exchange: str    = _EXCHANGE,
    screener: str    = _SCREENER,
    interval: str    = "1d",
    timeout: int     = 10,
) -> Optional[dict]:
    """
    TradingView'dan belirtilen BIST hissesi için teknik sinyal çeker.

    Args:
        symbol:   BIST sembolü, ör. "THYAO" (büyük/küçük harf fark etmez)
        exchange: Borsa kodu (varsayılan: "BIST")
        screener: TradingView screener (varsayılan: "turkey")
        interval: Zaman aralığı — "1m","5m","15m","1h","4h","1d","1W","1M"
        timeout:  İstek zaman aşımı (saniye)

    Returns:
        dict: {
            symbol, tv_recommendation, tv_recommendation_tr,
            tv_buy_count, tv_sell_count, tv_neutral_count,
            tv_score, interval, fetched_at
        }
        None: Hata durumunda — programı çökertmez.
    """
    if not _TV_AVAILABLE:
        logger.error("tradingview-ta paketi yuklu degil.")
        return None

    symbol_upper = symbol.upper().strip()
    interval_obj = _get_interval(interval)

    try:
        handler = TA_Handler(
            symbol   = symbol_upper,
            screener = screener,
            exchange = exchange,
            interval = interval_obj,
        )
        analysis = handler.get_analysis()
        summary  = analysis.summary  # {'RECOMMENDATION': ..., 'BUY': n, 'SELL': n, 'NEUTRAL': n}

        buy     = summary.get("BUY",     0)
        sell    = summary.get("SELL",    0)
        neutral = summary.get("NEUTRAL", 0)
        rec     = summary.get("RECOMMENDATION", "NEUTRAL")

        score = _compute_tv_score(buy, sell, neutral)

        result = {
            "symbol":               symbol_upper,
            "tv_recommendation":    rec,
            "tv_recommendation_tr": _recommendation_to_str(rec),
            "tv_buy_count":         buy,
            "tv_sell_count":        sell,
            "tv_neutral_count":     neutral,
            "tv_score":             score,
            "interval":             interval,
            "fetched_at":           datetime.now(tz=timezone.utc).isoformat(),
        }
        logger.info(
            "TV sinyal: %s | %s | Skor: %.1f | AL:%d SAT:%d NOTR:%d",
            symbol_upper, rec, score, buy, sell, neutral,
        )
        return result

    except (ValueError, ConnectionError, TimeoutError) as exc:
        logger.warning("TV sinyal ag/baglanti hatasi (%s): %s", symbol_upper, exc)
        return None


# ---------------------------------------------------------------------------
# Toplu sinyal çekme
# ---------------------------------------------------------------------------

def fetch_tv_signals_batch(
    symbols: list[str],
    exchange: str = _EXCHANGE,
    screener: str = _SCREENER,
    interval: str = "1d",
    delay:    float = _DELAY_BETWEEN_REQUESTS,
) -> list[dict]:
    """
    Watchlist'teki tüm semboller için TradingView sinyali çeker.

    Args:
        symbols:  Sembol listesi, ör. ["THYAO", "ASELS", "GARAN"]
        exchange: Borsa kodu
        screener: TradingView screener
        interval: Zaman aralığı
        delay:    Semboller arası bekleme süresi (saniye)

    Returns:
        list[dict]: Başarılı sinyallerin listesi (hatalı semboller atlanır)
    """
    results: list[dict] = []
    for i, symbol in enumerate(symbols):
        signal = fetch_tv_signal(
            symbol   = symbol,
            exchange = exchange,
            screener = screener,
            interval = interval,
        )
        if signal:
            results.append(signal)
        if i < len(symbols) - 1:
            time.sleep(delay)

    logger.info(
        "TV toplu sinyal: %d/%d sembol basarili.",
        len(results), len(symbols),
    )
    return results


# ---------------------------------------------------------------------------
# Örnek çalıştırma — `python -m news.tv_signals`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import yaml
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    settings_path = Path("config/settings.yaml")
    example_path  = Path("config/settings.example.yaml")
    config_file   = settings_path if settings_path.exists() else example_path

    with open(config_file, encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    watchlist = settings.get("watchlist", ["THYAO", "ASELS", "SISE", "GARAN", "KCHOL"])
    tv_cfg    = settings.get("tradingview", {})
    interval  = tv_cfg.get("interval", "1d")

    print(f"\n{'='*65}")
    print(f"  TradingView Teknik Sinyal Çekici — BIST (interval: {interval})")
    print(f"{'='*65}\n")

    signals = fetch_tv_signals_batch(symbols=watchlist, interval=interval)

    if not signals:
        print("Hiç sinyal alinamadi. Internet baglantisini ve sembolleri kontrol edin.")
    else:
        print(f"\n{'Sembol':<8} {'TV Öneri':<14} {'Skor':>5}  {'AL':>4} {'SAT':>4} {'NÖTR':>5}")
        print("-" * 50)
        for s in signals:
            rec_tr = s.get("tv_recommendation_tr", "-")
            print(
                f"{s['symbol']:<8} {rec_tr:<14} {s['tv_score']:>5.1f}"
                f"  {s['tv_buy_count']:>4} {s['tv_sell_count']:>4} {s['tv_neutral_count']:>5}"
            )
        print()
        avg_score = sum(s["tv_score"] for s in signals) / len(signals)
        print(f"  Ortalama TV Skoru: {avg_score:.1f}/100")
        print(f"  Toplam sinyal alindi: {len(signals)}/{len(watchlist)} sembol")
