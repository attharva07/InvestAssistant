import logging
import re
from datetime import date, datetime, timezone

import pandas as pd
import yfinance as yf

from backend.database import db_cursor

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _validate_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if not _TICKER_RE.match(t):
        raise ValueError(f"Invalid ticker symbol: {ticker!r}")
    return t


def get_cached_close(ticker: str, as_of: str) -> float | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT close FROM price_cache WHERE ticker=? AND as_of_date=?",
            (ticker, as_of),
        )
        row = cur.fetchone()
    return float(row["close"]) if row else None


def set_cached_close(ticker: str, as_of: str, close: float) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO price_cache(ticker,as_of_date,close,retrieved_at)
            VALUES(?,?,?,?)
            ON CONFLICT(ticker,as_of_date)
            DO UPDATE SET close=excluded.close, retrieved_at=excluded.retrieved_at
            """,
            (ticker, as_of, close, datetime.now(timezone.utc).isoformat()),
        )


def get_latest_close(ticker: str) -> tuple[float | None, bool]:
    ticker = _validate_ticker(ticker)
    today = date.today().isoformat()
    cached = get_cached_close(ticker, today)
    if cached is not None:
        return cached, False
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
        if hist.empty:
            raise ValueError("No price data")
        close = float(hist["Close"].dropna().iloc[-1])
        set_cached_close(ticker, today, close)
        return close, False
    except Exception:
        logger.warning("Failed to fetch price for %s, falling back to cache", ticker)
        with db_cursor() as cur:
            cur.execute(
                "SELECT close FROM price_cache WHERE ticker=? ORDER BY as_of_date DESC LIMIT 1",
                (ticker,),
            )
            row = cur.fetchone()
        if row:
            return float(row["close"]), True
        return None, True


def get_history(ticker: str, period: str = "6mo") -> tuple[pd.DataFrame, bool]:
    ticker = _validate_ticker(ticker)
    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
        if hist.empty:
            raise ValueError("No data")
        return hist, False
    except Exception:
        logger.warning("Failed to fetch history for %s", ticker)
        return pd.DataFrame(), True
