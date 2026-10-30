"""
backtest/news_backtest.py
-------------------------
Yapay Zeka (LLM) tarafindan uretilen hisse bazli haber duyarlilik skorlarini (Tarihsel Haberler) 
Teknik Analiz (RSI vb.) ile birlestirerek 6 aylik (veya veri olan donem) backtest yapar.
- Normal (Sadece Teknik) vs AI Haber Destekli performanslari karsilastirir.
"""

import logging
import sqlite3
import pandas as pd
import numpy as np
from datetime import timedelta
from pathlib import Path

from backtest.simple_backtest import run_backtest, _empty_result
from data.price_fetcher import load_prices
from indicators.technical import calculate_indicators
from signals.signal_engine import _technical_score

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)

def load_historical_news_scores(db_path: str = "data/news/news.db") -> pd.DataFrame:
    """
    news ve analyzed tablolarini join'leyerek tum tarihsel haber skorlarini bir DataFrame olarak dondurur.
    Kolonlar: date, symbol, sentiment_score, weight
    """
    db_path_obj = Path(db_path)
    if not db_path_obj.exists():
        logger.warning(f"Veritabani bulunamadi: {db_path}")
        return pd.DataFrame()
        
    query = """
    SELECT n.date, n.symbol_mentions, a.sentiment, a.confidence
    FROM news n
    INNER JOIN analyzed a ON n.link = a.link
    WHERE n.symbol_mentions != '' AND a.sentiment IS NOT NULL
    """
    
    with sqlite3.connect(db_path_obj) as conn:
        df = pd.read_sql_query(query, conn)
        
    if df.empty:
        return df
        
    # Tarihi datetime'a cevir
    df["date"] = pd.to_datetime(df["date"], errors='coerce', utc=True).dt.tz_localize(None)
    
    # Sentiment text -> score (0-100)
    sentiment_map = {"positive": 100.0, "neutral": 50.0, "negative": 0.0}
    df["sentiment_score"] = df["sentiment"].str.lower().map(sentiment_map).fillna(50.0)
    df["weight"] = pd.to_numeric(df["confidence"], errors='coerce').fillna(50.0) / 100.0
    
    return df

def get_7day_rolling_news_score(news_df: pd.DataFrame, symbol: str, target_date: pd.Timestamp) -> float:
    """
    Hedef tarihten onceki 7 gun icindeki o hisseye ait haberlerin ortalama skorunu hesaplar.
    Haber yoksa 50 dondurur.
    """
    if news_df.empty:
        return 50.0
        
    start_date = target_date - timedelta(days=7)
    
    # Filtrele: Hissenin haberi mi? Zaman araliginda mi?
    mask = (news_df["symbol_mentions"].str.contains(symbol, na=False, case=False)) & \
           (news_df["date"] > start_date) & \
           (news_df["date"] <= target_date)
           
    recent_news = news_df.loc[mask]
    
    if recent_news.empty:
        return 50.0
        
    # Agirlikli ortalama
    weighted_sum = (recent_news["sentiment_score"] * recent_news["weight"]).sum()
    total_weight = recent_news["weight"].sum()
    
    if total_weight > 0:
        return round(weighted_sum / total_weight, 1)
    return 50.0

def run_comparative_backtest():
    capital = 100000.0
    
    print(f"\n{'='*72}")
    print(f"  YAPAY ZEKA (LLM) HABER DESTEKLI BACKTEST MOTORU")
    print(f"  Baslangic Sermayesi: {capital:,.0f} TL | Donem: Son 6 Ay")
    print(f"{'='*72}")
    
    news_df = load_historical_news_scores()
    if news_df.empty:
        print("Hata: Veritabaninda LLM tarafindan analiz edilmis haber bulunamadi.")
        print("Lutfen once `daily_routine.py` veya `llm/news_analyzer.py` calistirin.")
        return
        
    print(f"Veritabanindan {len(news_df)} adet LLM puanli haber yuklendi.")
    
    # XU100 Verisini Yukle (Piyasa Rejimi icin)
    xu100_df_raw = load_prices("XU100", folder="data/raw")
    if not xu100_df_raw.empty:
        xu100_df = calculate_indicators(xu100_df_raw)
    else:
        print("Uyari: XU100 verisi bulunamadi, Piyasa Rejimi filtresi calismayacak.")
        xu100_df = None
    
    test_stocks = ["PGSUS", "MIATK", "YEOTK", "CCOLA", "SISE", "ENKAI", "YKBNK", "TUPRS", "FROTO", "BIMAS"]
    
    results = []
    
    for sym in test_stocks:
        df = load_prices(sym, folder="data/raw")
        if df.empty:
            continue
            
        # Son 6 ayi filtrele
        six_months_ago = pd.Timestamp.now() - pd.DateOffset(months=6)
        # Indicator hesabi icin biraz oncesini de almak lazim
        eight_months_ago = pd.Timestamp.now() - pd.DateOffset(months=8)
        
        df = df[df.index >= eight_months_ago].copy()
        if df.empty:
            continue
            
        df_ind = calculate_indicators(df)
        
        # Test periyodunu kesin 6 ay yapalim (Indicator isinmasi bittikten sonrasi)
        test_df = df_ind[df_ind.index >= six_months_ago].copy()
        
        if test_df.empty:
            continue
            
        # --- SADECE TEKNIK SKOR ---
        tech_scores_dict = {}
        ai_combined_scores_dict = {}
        
        for date, row in test_df.iterrows():
            # Teknik skor hesabi (XU100 rejimi dahil)
            window = df_ind.loc[:date]
            tech_score, _ = _technical_score(window, xu100_df=xu100_df)
            tech_scores_dict[date] = tech_score
            
            # Haber (LLM) Skoru hesabi (son 7 gun)
            news_score = get_7day_rolling_news_score(news_df, sym, date)
            
            # Birlestirilmis Skor: %50 Teknik, %50 Haber
            # Eger hic haber yoksa (news_score=50), teknik skorun onemi daha fazla olsun
            if news_score == 50.0:
                combined = tech_score
            else:
                combined = (tech_score * 0.4) + (news_score * 0.6) # Haber daha etkili (Ozellikle kisa vadede)
            
            ai_combined_scores_dict[date] = combined
            
        tech_series = pd.Series(tech_scores_dict)
        ai_series = pd.Series(ai_combined_scores_dict)
        
        # Backtest 1: Sadece Teknik
        bt_tech = run_backtest(
            test_df, initial_capital=capital,
            signal_scores=tech_series,
            score_buy_threshold=70.0,
            score_sell_threshold=30.0
        )
        
        # Backtest 2: AI Haber + Teknik
        bt_ai = run_backtest(
            test_df, initial_capital=capital,
            signal_scores=ai_series,
            score_buy_threshold=70.0,
            score_sell_threshold=30.0
        )
        
        results.append({
            "Hisse"       : sym,
            "Klasik Get%" : f"{bt_tech['total_return']:+.1f}",
            "Klasik Win%" : f"{bt_tech['win_rate']*100:.0f}",
            "Klasik Islem": bt_tech["num_trades"],
            "AI+Haber Get%": f"{bt_ai['total_return']:+.1f}",
            "AI Win%"     : f"{bt_ai['win_rate']*100:.0f}",
            "AI Islem"    : bt_ai["num_trades"],
            "FARK"        : f"{bt_ai['total_return'] - bt_tech['total_return']:+.1f}"
        })
        
    print("\n--- 6 AYLIK SONUCLAR: SADECE TEKNIK vs AI HABER DESTEKLI ---")
    print(pd.DataFrame(results).to_string(index=False))
    print("\nNOT: Eger 'FARK' pozitif ise, yapay zekaniz haberleri okuyarak ekstra kar/zarardan kacinma basarisi gostermis demektir.")

if __name__ == "__main__":
    run_comparative_backtest()
