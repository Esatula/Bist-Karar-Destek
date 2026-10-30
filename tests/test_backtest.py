"""
tests/test_backtest.py
----------------------
backtest.portfolio_backtest modülü için sentetik veri kullanan birim testler.
"""
import numpy as np
import pandas as pd
import pytest

from indicators.technical import calculate_indicators
from backtest.portfolio_backtest import run_portfolio_backtest, _empty_result

def make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0, 1.5, n))
    close = np.maximum(close, 1.0)
    high = close + rng.uniform(0, 3, n)
    low = close - rng.uniform(0, 3, n)
    low = np.maximum(low, 0.5)
    open_ = low + rng.uniform(0, (high - low), n)
    volume = rng.integers(100_000, 5_000_000, n).astype(float)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates)

class TestRunPortfolioBacktest:
    def test_empty_input(self):
        result = run_portfolio_backtest({}, {})
        assert result["total_return"] == 0.0
        assert result["num_trades"] == 0
        
    def test_basic_trade_logic(self):
        # Create a simple synthetic scenario for THYAO
        df = make_ohlcv(50)
        df_ind = calculate_indicators(df)
        
        # Artificial signals: Buy on day 10, Sell on day 30
        scores = pd.Series(50, index=df.index)
        scores.iloc[10] = 80 # Buy signal
        scores.iloc[30] = 30 # Sell signal
        
        dfs = {"THYAO": df_ind}
        signal_scores = {"THYAO": scores}
        
        result = run_portfolio_backtest(
            dfs, 
            signal_scores, 
            initial_capital=100_000, 
            use_atr_dynamic=False, 
            score_buy_threshold=70, 
            score_sell_threshold=40
        )
        
        # Since we trigger buy on index 10 and sell on index 30, we expect 1 trade
        assert result["num_trades"] == 1
        assert len(result["trades"]) == 1
        assert result["trades"][0]["symbol"] == "THYAO"

    def test_max_drawdown_negative(self):
        df = make_ohlcv(100)
        df_ind = calculate_indicators(df)
        
        scores = pd.Series(50, index=df.index)
        scores.iloc[5:90] = 80 # Hold for a long time
        
        dfs = {"THYAO": df_ind}
        signal_scores = {"THYAO": scores}
        
        result = run_portfolio_backtest(dfs, signal_scores)
        assert result["max_drawdown"] <= 0.0

    def test_slippage_and_commission(self):
        df = make_ohlcv(50)
        df_ind = calculate_indicators(df)
        
        scores = pd.Series(50, index=df.index)
        scores.iloc[10] = 90
        scores.iloc[20] = 20
        
        dfs = {"THYAO": df_ind}
        signal_scores = {"THYAO": scores}
        
        r_low_cost = run_portfolio_backtest(dfs, signal_scores, commission_pct=0.0, slippage_pct=0.0, use_atr_dynamic=False)
        r_high_cost = run_portfolio_backtest(dfs, signal_scores, commission_pct=1.0, slippage_pct=1.0, use_atr_dynamic=False)
        
        assert r_low_cost["final_capital"] > r_high_cost["final_capital"]
