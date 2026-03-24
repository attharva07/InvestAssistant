"""
/finance/trades — manual trade entry and history.
"""
import json
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.database import db_cursor
from backend.services.portfolio_service import insert_events, rebuild_holdings

router = APIRouter(prefix="/finance/trades", tags=["finance-trades"])


class TradeCreate(BaseModel):
    ticker: str
    action: Literal["BUY", "SELL"]
    shares: float
    price: float
    trade_date: str  # ISO date string e.g. "2024-01-15"
    description: str | None = None


@router.post("")
def log_trade(payload: TradeCreate):
    """Log a manual BUY or SELL trade."""
    event = {
        "source": "manual",
        "event_type": payload.action,
        "ticker": payload.ticker.strip().upper(),
        "quantity": payload.shares,
        "price": payload.price,
        "amount": round(payload.shares * payload.price, 4),
        "currency": "USD",
        "event_ts": payload.trade_date if "T" in payload.trade_date else payload.trade_date + "T00:00:00+00:00",
        "description": payload.description or f"{payload.action} {payload.shares} {payload.ticker} @ {payload.price}",
        "recommendation_id": None,
    }
    event["raw_json"] = json.dumps(event)
    inserted = insert_events([event])
    holdings_count = rebuild_holdings()
    return {"inserted": inserted, "holdings_count": holdings_count, "trade": event}


@router.get("")
def list_trades(
    ticker: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    """Return trade history, optionally filtered by ticker or action."""
    conditions = ["event_type IN ('BUY','SELL')"]
    params: list = []
    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker.strip().upper())
    if action:
        conditions.append("event_type = ?")
        params.append(action.upper())
    where = " AND ".join(conditions)
    with db_cursor() as cur:
        cur.execute(
            f"SELECT id, event_type, ticker, quantity, price, amount, event_ts, description, source "
            f"FROM events WHERE {where} ORDER BY event_ts DESC LIMIT ?",
            params + [limit],
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"trades": rows, "count": len(rows)}
