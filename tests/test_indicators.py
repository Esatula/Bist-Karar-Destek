import numpy as np
import pandas as pd
import pytest
from indicators.technical import calculate_indicators

def test_calculate_indicators_missing_columns():
    df = pd.DataFrame({"Close": [10, 20]})
    with pytest.raises(ValueError, match="eksik kolon"):
        calculate_indicators(df)

def test_calculate_indicators_success():
    dates = pd.date_range("2024-01-01", periods=100)
    df = pd.DataFrame({
        "Open": np.random.rand(100) * 100,
        "High": np.random.rand(100) * 100 + 10,
        "Low": np.random.rand(100) * 100 - 10,
        "Close": np.random.rand(100) * 100,
        "Volume": np.random.randint(1000, 10000, 100)
    }, index=dates)
    
    result = calculate_indicators(df)
    
    expected_cols = [
        "EMA_20", "EMA_50", "RSI_14", "MACD", "MACD_signal",
        "ATR_14", "ADX_14", "BB_UPPER_20", "OBV"
    ]
    for col in expected_cols:
        assert col in result.columns

    assert len(result) == 100
