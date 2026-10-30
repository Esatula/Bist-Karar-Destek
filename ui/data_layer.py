import streamlit as st
import pandas as pd
from typing import Tuple

from config.manager import config
from data.price_fetcher import load_prices
from signals.signal_engine import generate_signal

@st.cache_data(ttl=300)
def get_detail(sym: str) -> Tuple[pd.DataFrame, dict, list]:
    """
    Fetches stock data and generates a signal.
    Cached for 5 minutes to avoid redundant API calls and processing.
    """
    df = load_prices(sym)
    if df is None or df.empty:
        return None, {}, []
        
    cfg = config.get_all()
    weights = cfg.get("signal_weights", {"technical": 0.8, "tradingview": 0.2})
    thresholds = cfg.get("signal_thresholds", {"buy": 70, "sell": 30})
    db_path = cfg.get("storage", {}).get("news_db_path", "data/news/news.db")
    
    # generate_signal handles calculating indicators, fetching TV signal,
    # evaluating red flags, and computing the final score.
    signal_res = generate_signal(
        symbol=sym,
        price_df=df,
        weights=weights,
        db_path=db_path,
        buy_threshold=thresholds.get("buy", 70),
        sell_threshold=thresholds.get("sell", 30)
    )

    # Convert recommendation to emoji format expected by UI
    rec = signal_res["recommendation"]
    rec_str = "🟢 AL" if rec == "AL" else "🔴 SAT" if rec == "SAT" else "⚪ BEKLE"

    comp = signal_res.get("components", {})
    
    signal = {
        "final":    signal_res["final_score"],
        "tech":     signal_res["technical_score"],
        "tv":       signal_res["tv_score"],
        "rec":      rec_str,
        "reason":   comp.get("signal_reason", "-"),
        "trend":    comp.get("trend_bullish"),
        "momentum": comp.get("momentum_bullish"),
        "volume":   comp.get("volume_bullish"),
        "market":   comp.get("market_bullish"),
        "fundamental": not comp.get("is_red_flag", False),
        "red_reason": comp.get("red_flag_reason", ""),
        "rsi":      comp.get("rsi"),
        "tv_rec":   signal_res.get("tv_recommendation", "YOK"),
    }

    news = []

    return df, signal, news
