from datetime import date, datetime

import pandas as pd
import yfinance as yf

from backend.database import db_cursor


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
            (ticker, as_of, close, datetime.utcnow().isoformat() + "Z"),
        )


def get_latest_close(ticker: str) -> tuple[float | None, bool]:
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
    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
        if hist.empty:
            raise ValueError("No data")
        return hist, False
    except Exception:
        return pd.DataFrame(), True
