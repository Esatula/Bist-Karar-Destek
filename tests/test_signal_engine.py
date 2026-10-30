import pandas as pd
import pytest
from unittest.mock import patch
from signals.signal_engine import _technical_score, generate_signal

def test_technical_score_empty():
    score, comp = _technical_score(None)
    assert score == 50.0
    
    score, comp = _technical_score(pd.DataFrame())
    assert score == 50.0

def test_technical_score_missing_cols():
    df = pd.DataFrame({"Close": [1, 2]})
    score, comp = _technical_score(df)
    assert score == 50.0

def test_technical_score_strong_buy():
    # Güçlü AL durumu: trend var, momentum pozitif, hacim onaylı
    data = {
        "EMA_20": [90],
        "EMA_50": [80],
        "Close": [100],
        "RSI_14": [60],
        "MACD": [2],
        "MACD_signal": [1],
        "Volume": [2000],
        "Volume_SMA_20": [500],
        "OBV": [10000],
        "ADX_14": [30],
        "ATR_14": [2],
        "BB_UPPER_20": [120],
        "BB_LOWER_20": [80]
    }
    df = pd.DataFrame(data, index=["2024-01-01"])
    score, comp = _technical_score(df)
    assert score == 85.0
    assert comp["trend_bullish"] is True
    assert comp["momentum_bullish"] is True
    assert comp["volume_bullish"] is True

def test_technical_score_strong_sell():
    # Güçlü SAT durumu: düşüş trendi, negatif momentum
    data = {
        "EMA_20": [80],
        "EMA_50": [90],
        "Close": [70],
        "RSI_14": [40],
        "MACD": [-2],
        "MACD_signal": [-1],
        "Volume": [1000],
        "Volume_SMA_20": [1500],
        "OBV": [9000],
        "ADX_14": [30],
        "ATR_14": [2],
        "BB_UPPER_20": [100],
        "BB_LOWER_20": [60]
    }
    df = pd.DataFrame(data, index=["2024-01-01"])
    score, comp = _technical_score(df)
    assert score == 28.0
    assert comp["trend_bullish"] is False
    assert comp["momentum_bullish"] is False

@patch("signals.signal_engine.check_fundamental_red_flags")
def test_generate_signal_basic(mock_flags):
    mock_flags.return_value = (False, "")
    
    # generate_signal uses calculate_indicators if RSI_14 is missing
    # we can provide a df that has required columns so it doesn't calculate
    data = {
        "EMA_20": [90], "EMA_50": [80], "Close": [100], "RSI_14": [60],
        "MACD": [2], "MACD_signal": [1], "Volume": [2000], "Volume_SMA_20": [500],
        "OBV": [10000], "ADX_14": [30], "ATR_14": [2], "BB_UPPER_20": [120], "BB_LOWER_20": [80]
    }
    df = pd.DataFrame(data, index=["2024-01-01"])
    
    tv_sig = {
        "tv_score": 80.0,
        "tv_recommendation_tr": "AL",
        "tv_buy_count": 12,
        "tv_sell_count": 2
    }
    
    res = generate_signal(
        "THYAO", 
        df, 
        weights={"technical": 0.5, "tradingview": 0.5},
        tv_signal=tv_sig
    )
    
    assert res["symbol"] == "THYAO"
    assert res["technical_score"] == 85.0
    assert res["tv_score"] == 80.0
    # Final score = 85*0.5 + 80*0.5 = 42.5 + 40 = 82.5
    assert res["final_score"] == 82.5
    assert res["recommendation"] == "AL"
