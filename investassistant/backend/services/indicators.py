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


def compute_sma(hist: pd.DataFrame, window: int) -> float | None:
    if hist.empty or "Close" not in hist.columns or len(hist) < window:
        return None
    val = hist["Close"].rolling(window=window).mean().iloc[-1]
    return float(val) if pd.notna(val) else None


def compute_ema(hist: pd.DataFrame, window: int) -> float | None:
    if hist.empty or "Close" not in hist.columns or len(hist) < window:
        return None
    val = hist["Close"].ewm(span=window, adjust=False).mean().iloc[-1]
    return float(val) if pd.notna(val) else None


def compute_volume_ratio(hist: pd.DataFrame, avg_window: int = 20) -> float | None:
    """Ratio of latest volume to N-day average volume."""
    if hist.empty or "Volume" not in hist.columns or len(hist) < avg_window + 1:
        return None
    avg_vol = float(hist["Volume"].iloc[-(avg_window + 1):-1].mean())
    if avg_vol == 0:
        return None
    current_vol = float(hist["Volume"].iloc[-1])
    return round(current_vol / avg_vol, 2)


def compute_macd(hist: pd.DataFrame) -> dict[str, float | None]:
    """Return MACD line, signal line, and histogram."""
    ema12 = compute_ema(hist, 12)
    ema26 = compute_ema(hist, 26)
    if ema12 is None or ema26 is None:
        return {"macd": None, "signal": None, "histogram": None}
    macd_line = ema12 - ema26
    # Signal = 9-period EMA of MACD values — approximate with latest value
    if len(hist) >= 35:
        macd_series = hist["Close"].ewm(span=12, adjust=False).mean() - hist["Close"].ewm(span=26, adjust=False).mean()
        signal_val = macd_series.ewm(span=9, adjust=False).mean().iloc[-1]
        signal = float(signal_val) if pd.notna(signal_val) else None
    else:
        signal = None
    histogram = round(macd_line - signal, 4) if signal is not None else None
    return {"macd": round(macd_line, 4), "signal": round(signal, 4) if signal else None, "histogram": histogram}


def build_written_reasoning(
    ticker: str,
    close: float,
    sma20: float | None,
    sma50: float | None,
    rsi: float | None,
    macd: dict,
    volume_ratio: float | None,
    drawdown: float | None,
) -> str:
    parts: list[str] = [f"{ticker} is currently trading at ${close:.2f}."]

    if sma50 is not None:
        if close > sma50:
            parts.append(f"Price is above the 50-day SMA (${sma50:.2f}), indicating a positive medium-term trend.")
        else:
            parts.append(f"Price is below the 50-day SMA (${sma50:.2f}), indicating bearish medium-term pressure.")

    if sma20 is not None:
        if close > sma20:
            parts.append(f"Short-term momentum is positive — price above the 20-day SMA (${sma20:.2f}).")
        else:
            parts.append(f"Short-term momentum is weak — price below the 20-day SMA (${sma20:.2f}).")

    if rsi is not None:
        if rsi > 70:
            parts.append(f"RSI of {rsi:.1f} signals overbought conditions; caution on new entries.")
        elif rsi < 30:
            parts.append(f"RSI of {rsi:.1f} signals oversold conditions; potential reversal opportunity.")
        else:
            parts.append(f"RSI of {rsi:.1f} is in neutral territory — no extreme momentum signal.")

    if macd.get("macd") is not None and macd.get("signal") is not None:
        m, s = macd["macd"], macd["signal"]
        if m > s:
            parts.append(f"MACD ({m:.3f}) is above signal ({s:.3f}), suggesting bullish momentum.")
        else:
            parts.append(f"MACD ({m:.3f}) is below signal ({s:.3f}), suggesting bearish momentum.")

    if volume_ratio is not None:
        if volume_ratio > 1.5:
            parts.append(f"Volume is {volume_ratio:.1f}x the 20-day average — elevated trading activity.")
        elif volume_ratio < 0.7:
            parts.append(f"Volume is low ({volume_ratio:.1f}x average), suggesting weak conviction in the move.")

    if drawdown is not None and drawdown < -10:
        parts.append(f"Price is {abs(drawdown):.1f}% below its 6-month high — in a notable drawdown.")

    # Overall sentiment
    bullish_signals = sum([
        close > (sma50 or 0),
        close > (sma20 or 0),
        rsi is not None and 30 < rsi < 65,
        macd.get("macd") is not None and macd.get("signal") is not None and macd["macd"] > macd["signal"],
    ])
    total_signals = 4
    if bullish_signals >= 3:
        sentiment = "BULLISH"
    elif bullish_signals <= 1:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    parts.append(f"Overall technical sentiment: {sentiment}.")
    return " ".join(parts)
