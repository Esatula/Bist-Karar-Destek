"""
indicators/technical.py
-----------------------
Saf pandas/numpy ile BIST teknik gösterge hesaplamaları.
Harici teknik analiz kütüphanesi kullanılmaz (pandas-ta Python 3.14
uyumsuzluğu nedeniyle kaldırıldı).

Desteklenen göstergeler:
    EMA_20, EMA_50, EMA_200  — Üstel hareketli ortalama
    RSI_14                   — Göreceli güç endeksi
    MACD, MACD_signal        — MACD çizgisi ve sinyal çizgisi
    ATR_14                   — Ortalama gerçek aralık
    OBV                      — Denge hacmi

Kullanım:
    from indicators.technical import calculate_indicators
    df_with_ind = calculate_indicators(df)
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, span: int) -> pd.Series:
    """
    Üstel Hareketli Ortalama (EMA).

    Args:
        series: Fiyat serisi (genellikle Close)
        span:   EMA periyodu (ör. 20, 50, 200)

    Returns:
        EMA serisi (aynı index ile)
    """
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Göreceli Güç Endeksi (RSI) — Wilder smoothing yöntemi.

    Args:
        series: Kapanış fiyatı serisi
        period: RSI periyodu (varsayılan 14)

    Returns:
        0-100 aralığında RSI serisi
    """
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder smoothing: ilk değer SMA, sonrası EWM
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series]:
    """
    MACD (Moving Average Convergence Divergence).

    Args:
        series: Kapanış fiyatı serisi
        fast:   Hızlı EMA periyodu (varsayılan 12)
        slow:   Yavaş EMA periyodu (varsayılan 26)
        signal: Sinyal çizgisi EMA periyodu (varsayılan 9)

    Returns:
        (macd_line, signal_line) tuple'ı
    """
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    return macd_line, signal_line


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Ortalama Gerçek Aralık (ATR) — Wilder smoothing ile.

    True Range = max(H-L, |H-C_prev|, |L-C_prev|)

    Args:
        df:     High, Low, Close kolonlarını içeren DataFrame
        period: ATR periyodu (varsayılan 14)

    Returns:
        ATR serisi
    """
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return atr


def _obv(df: pd.DataFrame) -> pd.Series:
    """
    Denge Hacmi (On Balance Volume — OBV).

    Kapanış önceki günden yüksekse hacim eklenir,
    düşükse çıkarılır, eşitse değişmez.

    Args:
        df: Close ve Volume kolonlarını içeren DataFrame

    Returns:
        OBV serisi
    """
    direction = np.sign(df["Close"].diff()).fillna(0)
    obv = (direction * df["Volume"]).cumsum()
    return obv


# ---------------------------------------------------------------------------
# Ana fonksiyon öncesi yardımcılar (ADX ve Bollinger)
# ---------------------------------------------------------------------------

def _bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bantları.
    
    Returns:
        (üst_bant, orta_bant, alt_bant) tuple'ı
    """
    mid_band = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper_band = mid_band + (std * std_dev)
    lower_band = mid_band - (std * std_dev)
    return upper_band, mid_band, lower_band


def _adx(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Average Directional Index (ADX) ve Directional Indicators (+DI, -DI).
    Wilder'ın klasik hesaplaması.
    
    Returns:
        (adx, plus_di, minus_di) tuple'ı
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    
    # 1. True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    
    # 2. Directional Movement (+DM, -DM)
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)
    
    # 3. Smoothed TR ve DM (Wilder's Smoothing)
    def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
    atr = wilder_smooth(tr, period)
    plus_di = 100 * wilder_smooth(plus_dm, period) / atr
    minus_di = 100 * wilder_smooth(minus_dm, period) / atr
    
    # 4. Directional Index (DX) ve ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = wilder_smooth(dx, period)
    
    return adx, plus_di, minus_di

# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Verilen OHLCV DataFrame'ine teknik göstergeler ekler.

    Orijinal DataFrame'e dokunmaz; kopyası üzerinde çalışır.
    Tüm hesaplamalar saf pandas/numpy ile yapılır.

    Eklenen kolonlar:
        EMA_5, EMA_13, EMA_34, vb. — Üstel hareketli ortalamalar
        RSI_14                   — Göreceli güç endeksi (0-100)
        MACD                     — MACD çizgisi (EMA12 - EMA26)
        MACD_signal              — Sinyal çizgisi (EMA9 of MACD)
        MACD_fast                — Hızlı MACD çizgisi (EMA5 - EMA13)
        MACD_fast_signal         — Hızlı Sinyal çizgisi (EMA4 of MACD_fast)
        ATR_14                   — Ortalama gerçek aralık
        OBV                      — Denge hacmi

    Args:
        df: Open, High, Low, Close, Volume kolonlarını içeren DataFrame
            (index = tarih)

    Returns:
        Orijinal kolonlara ek gösterge kolonları eklenmiş yeni DataFrame.
        Yeterli veri yoksa NaN değerler içerebilir.

    Raises:
        ValueError: Gerekli kolonlar (Close, High, Low, Volume) yoksa
    """
    required = {"Close", "High", "Low", "Volume"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame'de eksik kolon(lar): {missing}")

    result = df.copy()

    # Üstel Hareketli Ortalamalar (Eskiler ve Yeniler)
    result["EMA_5"]   = _ema(result["Close"], 5)
    result["EMA_9"]   = _ema(result["Close"], 9)
    result["EMA_13"]  = _ema(result["Close"], 13)
    result["EMA_20"]  = _ema(result["Close"], 20)
    result["EMA_34"]  = _ema(result["Close"], 34)
    result["EMA_50"]  = _ema(result["Close"], 50)
    result["EMA_200"] = _ema(result["Close"], 200)

    # RSI (14 günlük)
    result["RSI_14"] = _rsi(result["Close"], period=14)

    # MACD ve sinyal çizgisi (Standart)
    result["MACD"], result["MACD_signal"] = _macd(result["Close"])
    
    # Hızlı MACD (Swing Trading için)
    result["MACD_fast"], result["MACD_fast_signal"] = _macd(result["Close"], fast=5, slow=13, signal=4)

    # ATR (14 günlük)
    result["ATR_14"] = _atr(result, period=14)

    # ADX ve DI (14 günlük)
    result["ADX_14"], result["PLUS_DI_14"], result["MINUS_DI_14"] = _adx(result, period=14)
    
    # Bollinger Bantları (20 günlük)
    result["BB_UPPER_20"], result["BB_MID_20"], result["BB_LOWER_20"] = _bollinger(result["Close"], period=20)

    # Hacim Ortalama (20 barlık)
    result["Volume_SMA_20"] = result["Volume"].rolling(window=20).mean()

    # OBV
    result["OBV"] = _obv(result)

    return result


# ---------------------------------------------------------------------------
# Örnek çalıştırma — `python -m indicators.technical`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pathlib import Path
    from data.price_fetcher import load_prices

    symbol = "THYAO"
    df = load_prices(symbol, folder="data/raw")

    if df.empty:
        print(f"Veri bulunamadi: {symbol}. Once `python -m data.price_fetcher` calistirin.")
    else:
        df_ind = calculate_indicators(df)
        print(f"\n{symbol} — Son 5 gun indikatör degerleri:")
        cols = ["Close", "EMA_20", "EMA_50", "EMA_200", "RSI_14", "MACD", "MACD_signal", "ATR_14"]
        print(df_ind[cols].tail(5).round(2).to_string())
        print(f"\nOBV (son 5): {df_ind['OBV'].tail(5).values}")
        print(f"\nToplam {len(df_ind)} satir, {len(df_ind.columns)} kolon.")
