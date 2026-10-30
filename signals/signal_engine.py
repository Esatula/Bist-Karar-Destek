"""
signals/signal_engine.py
------------------------
Teknik analiz + TradingView sinyali birleştiren sinyal motoru. (Sadeleştirilmiş Sürüm)

Teknik Alt-Skor (0-100):
    EMA Trendi   : Hızlı/yavaş EMA hiyerarşisi + ADX rejim tespiti
    RSI          : Aşırı satım/alım bölgelerinden uzaklık
    MACD         : MACD > sinyal çizgisi ise pozitif momentum
    Bollinger    : Yatay piyasada bant kenarlarına dayalı mean-reversion

TradingView Alt-Skoru (0-100):
    tradingview-ta kütüphanesiyle BIST hisselerinin TradingView teknik
    özeti çekilir (AL/SAT/NÖTR indikatör sayılarına dayalı 0-100 skor).
    TV sinyali alınamazsa bu bileşen sıfır ağırlığa düşer.

Final Skor = (teknik * w_teknik) + (tv * w_tv)
    TV sinyali yoksa: w_teknik 1.0 (100%) olur.

Öneri eşikleri (settings.yaml'dan okunur):
    final_score >= 70 → AL
    final_score <= 30 → SAT
    arası             → BEKLE

Kullanım:
    python -m signals.signal_engine
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from data.price_fetcher import load_prices
from data.fundamentals import check_fundamental_red_flags
from indicators.technical import calculate_indicators
from news.tv_signals import fetch_tv_signal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Teknik Alt-Skor
# ---------------------------------------------------------------------------

def technical_score(df: pd.DataFrame, xu100_df: Optional[pd.DataFrame] = None) -> tuple[float, dict]:
    if df is None or df.empty:
        return 50.0, {}

    required = ["EMA_20", "EMA_50", "RSI_14", "MACD", "MACD_signal",
                "Volume", "Volume_SMA_20", "OBV", "Close", "ADX_14", "BB_UPPER_20", "BB_LOWER_20"]
    missing = set(required) - set(df.columns)
    if missing:
        return 50.0, {}

    df_clean = df.dropna(subset=required)
    if df_clean.empty:
        return 50.0, {}

    last = df_clean.iloc[-1]
    components = {}

    market_bullish = True
    if xu100_df is not None and not xu100_df.empty:
        target_date = last.name
        xu100_row = None
        if target_date in xu100_df.index:
            xu100_row = xu100_df.loc[target_date]
        else:
            past = xu100_df[xu100_df.index <= target_date]
            if not past.empty:
                xu100_row = past.iloc[-1]
        if xu100_row is not None and "EMA_50" in xu100_df.columns:
            if pd.notna(xu100_row.get("EMA_50")) and xu100_row["Close"] < xu100_row["EMA_50"]:
                market_bullish = False

    components["market_bullish"] = market_bullish

    from config.manager import config
    t_params = config.get("technical_params", {})
        
    rsi_ob = t_params.get("rsi_overbought", 75)
    rsi_os = t_params.get("rsi_oversold", 30)
    macd_cap = t_params.get("macd_buy_cap", 55)
    adx_thresh = t_params.get("adx_ranging_threshold", 25.0)
    bb_low_mar = t_params.get("bb_lower_margin", 1.02)
    bb_up_mar  = t_params.get("bb_upper_margin", 0.98)
    atr_sl_mult = t_params.get("atr_stop_loss_multiplier", 2.0)
    atr_tp_mult = t_params.get("atr_take_profit_multiplier", 3.5)

    ema20    = last["EMA_20"]
    ema50    = last["EMA_50"]
    close    = last["Close"]
    rsi      = last["RSI_14"]
    macd     = last["MACD"]
    macd_sig = last["MACD_signal"]

    adx      = last.get("ADX_14", 25)
    atr      = last.get("ATR_14", 0)
    bb_lower = last.get("BB_LOWER_20", 0)
    bb_upper = last.get("BB_UPPER_20", float("inf"))
    is_ranging = adx < adx_thresh
    near_lower_bb = (close <= bb_lower * bb_low_mar)
    near_upper_bb = (close >= bb_upper * bb_up_mar)

    components["adx"] = round(adx, 1)
    components["regime"] = "YATAY" if is_ranging else "TREND"
    components["stop_loss"] = round(close - (atr_sl_mult * atr), 2)
    components["take_profit"] = round(close + (atr_tp_mult * atr), 2)

    trend_bullish    = bool((ema20 > ema50) and (close > ema20))
    components["trend_bullish"]  = trend_bullish
    components["ema20_vs_ema50"] = round(ema20 - ema50, 4)

    momentum_bullish = bool((macd > macd_sig) and (rsi > 50))
    components["momentum_bullish"] = momentum_bullish
    components["rsi"] = round(rsi, 1)

    vol_sma        = last["Volume_SMA_20"]
    vol_spike      = bool((vol_sma > 0) and (last["Volume"] > vol_sma * 2.0))
    obv_up         = bool((len(df_clean) >= 5) and (df_clean["OBV"].iloc[-1] > df_clean["OBV"].iloc[-5]))
    volume_bullish = bool(vol_spike or obv_up)
    components["volume_bullish"] = volume_bullish

    if rsi > rsi_ob or (is_ranging and near_upper_bb):
        score  = 30.0
        reason = f"Asiri Alim (RSI>{rsi_ob} veya BB Ust) -> SAT"
    elif rsi < rsi_os and not trend_bullish:
        score  = 25.0
        reason = "Asiri Satim + Dusus Trendi -> SAT"
    elif is_ranging and near_lower_bb and rsi < 45:
        score  = 75.0 if market_bullish else macd_cap
        reason = f"Yatay Piyasa BB Alt Band Tepkisi (ADX:{adx:.1f}) -> AL"
    elif rsi < rsi_os and trend_bullish and volume_bullish:
        score  = 75.0 if market_bullish else macd_cap
        reason = f"Dip Alim Firsati (RSI<{rsi_os} + Trend + Hacim)"
    elif trend_bullish and momentum_bullish and volume_bullish:
        score  = 85.0
        reason = "Guclu Trend + Momentum + Hacim (3lu Onay) -> Guclu AL"
    elif trend_bullish and momentum_bullish:
        score  = 68.0
        reason = "Trend + Momentum Onayi (Hacim Eksik) -> AL"
    elif trend_bullish and not momentum_bullish:
        score  = 52.0
        reason = "Trend Var, Momentum Zayif -> BEKLE"
    elif not trend_bullish and not momentum_bullish:
        score  = 28.0
        reason = "Dusus Trendi + Negatif Momentum -> SAT"
    else:
        score  = 45.0
        reason = "Kararsiz Piyasa -> BEKLE"

    if not market_bullish and score > macd_cap:
        score   = float(macd_cap)
        reason += f" [AYI PIYASASI: Puan {macd_cap}e dusuruldu - Nakit Koru]"

    components["signal_reason"]    = reason
    components["final_tech_score"] = round(score, 1)
    return round(score, 1), components


def _log_tv_signal(db_path: str, symbol: str, tv_signal: dict, current_price: float):
    try:
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        with sqlite3.connect(db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tv_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    date TEXT,
                    tv_recommendation TEXT,
                    tv_score REAL,
                    close_price REAL
                )
            ''')
            conn.execute('''
                INSERT INTO tv_history (symbol, date, tv_recommendation, tv_score, close_price)
                VALUES (?, ?, ?, ?, ?)
            ''', (symbol, date_str, tv_signal.get("tv_recommendation", "NEUTRAL"), tv_signal.get("tv_score", 50.0), current_price))
    except sqlite3.Error as e:
        logger.warning("TV signal log SQLite hatasi: %s", e)

def _evaluate_tv_reliability(symbol: str, price_df: pd.DataFrame, db_path: str) -> float:
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tv_history'")
            if not cur.fetchone():
                return 1.0
            cur = conn.execute("SELECT date, tv_score, close_price FROM tv_history WHERE symbol = ? ORDER BY date DESC LIMIT 20", (symbol,))
            rows = cur.fetchall()
            
        if len(rows) < 3: 
            return 1.0 
            
        success_count = 0
        valid_signals = 0
        current_price = price_df["Close"].iloc[-1]
        
        for row in rows:
            signal_date, tv_score, old_price = row
            if pd.isna(old_price) or old_price == 0:
                continue
                
            price_change = (current_price - old_price) / old_price
            
            if tv_score > 60:
                valid_signals += 1
                if price_change > 0.005: 
                    success_count += 1
            elif tv_score < 40:
                valid_signals += 1
                if price_change < -0.005:
                    success_count += 1
                    
        if valid_signals == 0:
            return 1.0
            
        return success_count / valid_signals
    except sqlite3.Error as e:
        logger.debug("TV reliability SQLite hesabi hatasi: %s", e)
        return 1.0


# ---------------------------------------------------------------------------
# Ana sinyal fonksiyonu
# ---------------------------------------------------------------------------

def generate_signal(
    symbol: str,
    price_df: pd.DataFrame,
    weights: Optional[dict] = None,
    tv_signal: Optional[dict] = None,
    tv_interval: str = "1d",
    db_path: str = "data/news/news.db",
    buy_threshold: float = 70.0,
    sell_threshold: float = 30.0,
    hold_threshold: float = 55.0,
    is_holding: bool = False,
    **kwargs
) -> dict:
    if weights is None:
        weights = {"technical": 0.8, "tradingview": 0.2}

    w_tech = weights.get("technical",    0.8)
    w_tv   = weights.get("tradingview",  0.2)
    
    # Eger orjinal weight config news barindiriyorsa, normalize edelim.
    if "news" in weights:
        total = w_tech + w_tv
        if total > 0:
            w_tech = w_tech / total
            w_tv = w_tv / total
        else:
            w_tech = 1.0
            w_tv = 0.0

    last_date = pd.to_datetime(price_df.index[-1]).replace(tzinfo=None)
    now = datetime.now().replace(tzinfo=None)
    days_old = (now - last_date).days

    if days_old > 4:
        logger.warning("%s fiyat verisi cok eski (%d gun). Guncel veri indirin.", symbol, days_old)
        return {
            "symbol": symbol,
            "final_score": 50.0,
            "technical_score": 50.0,
            "tv_score": 50.0,
            "tv_recommendation": "YOK",
            "recommendation": "VERİ ESKİ",
            "reasoning": f"Veri {days_old} gunluk. Lutfen `price_fetcher` calistirin.",
            "components": {}
        }

    if "RSI_14" not in price_df.columns:
        price_df = calculate_indicators(price_df)

    tech_score, components = technical_score(price_df)

    is_red_flag, red_flag_reason = check_fundamental_red_flags(symbol)
    components["is_red_flag"] = is_red_flag
    components["red_flag_reason"] = red_flag_reason
    
    if is_red_flag and tech_score > 65.0:
        logger.info("%s icin Kirmizi Bayrak devrede! Teknik skor %.1f -> 65.0'a dusuruldu. (%s)", symbol, tech_score, red_flag_reason)
        tech_score = 65.0

    if tv_signal is None:
        tv_signal = fetch_tv_signal(symbol=symbol, interval=tv_interval)
        if tv_signal and not price_df.empty:
            _log_tv_signal(db_path, symbol, tv_signal, price_df["Close"].iloc[-1])

    if tv_signal:
        tv_score_val       = tv_signal.get("tv_score", 50.0)
        tv_rec             = tv_signal.get("tv_recommendation_tr", "NÖTR")
        tv_buy_count       = tv_signal.get("tv_buy_count", 0)
        tv_sell_count      = tv_signal.get("tv_sell_count", 0)
        
        if not price_df.empty:
            tv_reliability = _evaluate_tv_reliability(symbol, price_df, db_path)
            if tv_reliability < 0.45:
                penalty = w_tv * 0.75 
                w_tv -= penalty
                w_tech += penalty
                logger.info("%s: TV Guvenilirligi dusuk (%.2f). TV Agirligi %%%.1f seviyesine indirildi.", 
                            symbol, tv_reliability, w_tv * 100)
    else:
        tv_score_val  = 50.0
        tv_rec        = "YOK"
        tv_buy_count  = 0
        tv_sell_count = 0
        w_tech = 1.0
        w_tv = 0.0
        logger.warning("%s: TV sinyali alinamadi, sadece teknik analiz kullanilacak.", symbol)

    final = round(
        w_tech * tech_score
        + w_tv   * tv_score_val,
        1,
    )

    if final >= buy_threshold:
        recommendation = "AL"
    elif final <= sell_threshold:
        recommendation = "SAT"
    else:
        if is_holding and final >= hold_threshold:
            recommendation = "TUT"
        else:
            recommendation = "BEKLE"

    ema_durum   = "hizli yukselis" if components.get("ema5_gt_13") else "dusus veya zayif trend"
    macd_durum  = "pozitif" if components.get("macd_bullish") else "negatif"
    rsi_val     = components.get("rsi_value", "?")
    tv_yorum = f"TV={tv_rec}({tv_buy_count}AL/{tv_sell_count}SAT)" if tv_signal else "TV=YOK"
    
    reasoning = (
        f"Teknik: {ema_durum}, RSI={rsi_val}, MACD {macd_durum}. "
        f"{tv_yorum}. "
    )
    
    if is_red_flag:
        reasoning += f"🚩 DİKKAT: {red_flag_reason}. "
        
    reasoning += (
        f"Skor: Teknik={tech_score:.0f}x{w_tech:.0%} + TV={tv_score_val:.0f}x{w_tv:.0%} "
        f"= {final:.0f}."
    )

    return {
        "symbol"          : symbol,
        "final_score"     : final,
        "technical_score" : tech_score,
        "tv_score"        : tv_score_val,
        "tv_recommendation": tv_rec,
        "recommendation"  : recommendation,
        "reasoning"       : reasoning,
        "components"      : components,
    }


if __name__ == "__main__":
    import logging
    from news.tv_signals import fetch_tv_signals_batch

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    from config.manager import config as cfg
    settings = cfg.get_all()

    watchlist    = settings["watchlist"]
    raw_folder   = settings["storage"]["price_data_folder"]
    db_path      = settings["storage"]["news_db_path"]
    weights      = settings.get("signal_weights", {"technical": 0.8, "tradingview": 0.2})
    thresholds   = settings.get("signal_thresholds", {"buy": 70, "sell": 30})
    tv_cfg       = settings.get("tradingview", {})
    tv_interval  = tv_cfg.get("interval", "1d")

    buy_thr  = thresholds.get("buy",  70)
    sell_thr = thresholds.get("sell", 30)

    print(f"\n{'='*75}")
    print(f"  BIST Sinyal Motoru (Teknik + TradingView)")
    tw = weights.get("technical", 0.8)
    tvw = weights.get("tradingview", 0.2)
    tot = tw + tvw
    print(f"  Agirliklar: Teknik={tw/tot:.0%} TV={tvw/tot:.0%}")
    print(f"  Esikler: AL>={buy_thr}  SAT<={sell_thr}  BEKLE arasi")
    print(f"{'='*75}\n")

    print("TradingView sinyalleri cekiliyor...")
    tv_signals_list = fetch_tv_signals_batch(symbols=watchlist, interval=tv_interval)
    tv_signals_map  = {s["symbol"]: s for s in tv_signals_list}
    print(f"  {len(tv_signals_list)}/{len(watchlist)} sembol icin TV sinyali alindi.\n")

    all_results = []
    for sym in watchlist:
        df = load_prices(sym, folder=raw_folder)
        if df.empty:
            logger.warning("%s: Fiyat verisi bulunamadi, atlaniyor.", sym)
            continue

        sig = generate_signal(
            symbol         = sym,
            price_df       = df,
            weights        = weights,
            tv_signal      = tv_signals_map.get(sym),
            tv_interval    = tv_interval,
            db_path        = db_path,
            buy_threshold  = buy_thr,
            sell_threshold = sell_thr,
        )
        all_results.append(sig)

    if not all_results:
        print("Hic sinyal uretilmedi.")
    else:
        summary_data = []
        for r in all_results:
            c = r["components"]
            summary_data.append({
                "Sembol"    : r["symbol"],
                "Öneri"     : r["recommendation"],
                "Skor"      : r["final_score"],
                "Teknik"    : r["technical_score"],
                "TV"        : r["tv_score"],
                "TV Öneri"  : r.get("tv_recommendation", "-"),
                "RSI"       : c.get("rsi_value", "?"),
                "MACD"      : "POZ" if c.get("macd_bullish") else "NEG",
            })

        df_out = pd.DataFrame(summary_data)
        print(df_out.to_string(index=False))

        print(f"\n{'-'*75}")
        print("Detayli gerekce:")
        for r in all_results:
            print(f"\n  [{r['recommendation']:5}] {r['symbol']}: {r['reasoning']}")
