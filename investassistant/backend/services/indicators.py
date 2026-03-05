import pandas as pd
from ta.momentum import RSIIndicator


def compute_rsi_14(hist: pd.DataFrame) -> float | None:
    if hist.empty or "Close" not in hist.columns or len(hist) < 14:
        return None
    rsi = RSIIndicator(close=hist["Close"], window=14).rsi()
    val = rsi.iloc[-1]
    return float(val) if pd.notna(val) else None


def drawdown_from_high(hist: pd.DataFrame) -> float | None:
    if hist.empty or "Close" not in hist.columns:
        return None
    close = float(hist["Close"].iloc[-1])
    high = float(hist["Close"].max())
    if high == 0:
        return None
    return ((close - high) / high) * 100
