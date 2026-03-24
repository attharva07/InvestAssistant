"""
/finance/analyze/{ticker} — RSI + MA + volume + sentiment + written reasoning.
"""
from fastapi import APIRouter, HTTPException

from backend.services.indicators import (
    build_written_reasoning,
    compute_ema,
    compute_macd,
    compute_rsi_14,
    compute_sma,
    compute_volume_ratio,
    drawdown_from_high,
)
from backend.services.market_data import get_history

router = APIRouter(prefix="/finance/analyze", tags=["finance-analyze"])


@router.get("/{ticker}")
def analyze_ticker(ticker: str):
    """
    Full technical analysis for a ticker:
    RSI(14), SMA(20/50), EMA(12/26), MACD, volume ratio,
    drawdown, sentiment label, and a written reasoning paragraph.
    """
    hist, delayed = get_history(ticker.strip().upper(), "6mo")
    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No price data found for '{ticker}'")

    close = float(hist["Close"].iloc[-1])
    rsi = compute_rsi_14(hist)
    sma20 = compute_sma(hist, 20)
    sma50 = compute_sma(hist, 50)
    ema12 = compute_ema(hist, 12)
    ema26 = compute_ema(hist, 26)
    macd = compute_macd(hist)
    volume_ratio = compute_volume_ratio(hist)
    drawdown = drawdown_from_high(hist)

    # Sentiment label
    bullish_count = sum([
        sma50 is not None and close > sma50,
        sma20 is not None and close > sma20,
        rsi is not None and 30 < rsi < 65,
        macd.get("macd") is not None and macd.get("signal") is not None and macd["macd"] > macd["signal"],
    ])
    if bullish_count >= 3:
        sentiment = "BULLISH"
    elif bullish_count <= 1:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    written_reasoning = build_written_reasoning(
        ticker=ticker.upper(),
        close=close,
        sma20=sma20,
        sma50=sma50,
        rsi=rsi,
        macd=macd,
        volume_ratio=volume_ratio,
        drawdown=drawdown,
    )

    return {
        "ticker": ticker.upper(),
        "current_price": round(close, 4),
        "data_delayed": delayed,
        "indicators": {
            "rsi_14": round(rsi, 2) if rsi is not None else None,
            "sma_20": round(sma20, 4) if sma20 is not None else None,
            "sma_50": round(sma50, 4) if sma50 is not None else None,
            "ema_12": round(ema12, 4) if ema12 is not None else None,
            "ema_26": round(ema26, 4) if ema26 is not None else None,
            "macd": macd,
            "volume_ratio_20d": volume_ratio,
            "drawdown_6mo_pct": round(drawdown, 2) if drawdown is not None else None,
        },
        "sentiment": sentiment,
        "written_reasoning": written_reasoning,
    }
