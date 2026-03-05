from datetime import datetime

from fastapi import APIRouter

from backend.database import db_cursor
from backend.services.indicators import compute_rsi_14, drawdown_from_high
from backend.services.market_data import get_history
from backend.services.portfolio_service import fetch_holdings

router = APIRouter(prefix="/report", tags=["report"])


def _get_watchlist() -> list[str]:
    with db_cursor() as cur:
        cur.execute("SELECT value FROM preferences WHERE key='watchlist'")
        row = cur.fetchone()
    if not row:
        return []
    return [x.strip().upper() for x in row["value"].split(",") if x.strip()]


@router.get("/daily")
def daily_report():
    tickers = {h["ticker"] for h in fetch_holdings()} | set(_get_watchlist())
    rows = []
    warnings = []
    for ticker in sorted(tickers):
        hist, delayed = get_history(ticker, "6mo")
        if hist.empty:
            rows.append(
                {
                    "ticker": ticker,
                    "close": None,
                    "change_1d_pct": None,
                    "change_1w_pct": None,
                    "rsi_14": None,
                    "drawdown_6mo_pct": None,
                    "risk_flags": ["no_data"],
                    "data_delayed": True,
                }
            )
            warnings.append(f"No recent data for {ticker}")
            continue

        close = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else close
        week = float(hist["Close"].iloc[-6]) if len(hist) > 5 else prev
        chg1d = ((close - prev) / prev) * 100 if prev else None
        chg1w = ((close - week) / week) * 100 if week else None
        rsi = compute_rsi_14(hist)
        drawdown = drawdown_from_high(hist)
        vol = hist["Close"].pct_change().dropna().tail(20).std() if len(hist) > 20 else None
        flags = []
        if rsi is not None and rsi > 70:
            flags.append("overbought")
        if rsi is not None and rsi < 30:
            flags.append("oversold")
        if vol is not None and vol > 0.04:
            flags.append("volatility_spike")

        rows.append(
            {
                "ticker": ticker,
                "close": close,
                "change_1d_pct": chg1d,
                "change_1w_pct": chg1w,
                "rsi_14": rsi,
                "drawdown_6mo_pct": drawdown,
                "risk_flags": flags,
                "data_delayed": delayed,
            }
        )
        if delayed:
            warnings.append(f"{ticker} data delayed (using stale/cached data if available)")

    return {"as_of": datetime.utcnow().isoformat() + "Z", "rows": rows, "warnings": warnings}
