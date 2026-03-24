"""
/finance/net-worth — snapshot + history.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from backend.database import db_cursor
from backend.services.market_data import get_latest_close
from backend.services.portfolio_service import fetch_holdings

router = APIRouter(prefix="/finance/net-worth", tags=["finance-net-worth"])

_NOW = lambda: datetime.now(timezone.utc).isoformat()


def _compute_net_worth() -> dict:
    """Calculate current net worth from all data sources."""
    # Portfolio value
    holdings = fetch_holdings()
    portfolio_value = 0.0
    for h in holdings:
        close, _ = get_latest_close(h["ticker"])
        portfolio_value += (close or 0.0) * h["shares"]

    with db_cursor() as cur:
        # Account balances
        cur.execute("SELECT COALESCE(SUM(balance), 0) as total FROM accounts")
        account_total = float(cur.fetchone()["total"])

        # Credit card balances (liabilities)
        cur.execute("SELECT COALESCE(SUM(current_balance), 0) as total FROM credit_cards")
        card_total = float(cur.fetchone()["total"])

        # Savings goals (already counted in accounts if funded from there, but track separately)
        cur.execute("SELECT COALESCE(SUM(current_amount), 0) as total FROM savings_goals")
        goals_total = float(cur.fetchone()["total"])

    total_assets = round(portfolio_value + account_total, 2)
    total_liabilities = round(card_total, 2)
    net_worth = round(total_assets - total_liabilities, 2)

    return {
        "portfolio_value": round(portfolio_value, 2),
        "account_balances": round(account_total, 2),
        "savings_goals_total": round(goals_total, 2),
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
    }


@router.get("")
def get_net_worth():
    """Return the current net worth calculation."""
    data = _compute_net_worth()
    data["as_of"] = _NOW()
    return data


@router.post("/snapshot")
def save_snapshot():
    """Compute and persist a net worth snapshot to history."""
    data = _compute_net_worth()
    now = _NOW()
    today = now[:10]
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO net_worth_log(total_assets, total_liabilities, net_worth, snapshot_date, created_at) "
            "VALUES(?,?,?,?,?)",
            (data["total_assets"], data["total_liabilities"], data["net_worth"], today, now),
        )
        snapshot_id = cur.lastrowid
    return {**data, "snapshot_id": snapshot_id, "snapshot_date": today, "created_at": now}


@router.get("/history")
def get_history(limit: int = Query(default=90, le=365)):
    """Return historical net worth snapshots."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM net_worth_log ORDER BY snapshot_date DESC LIMIT ?", (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"history": rows, "count": len(rows)}
