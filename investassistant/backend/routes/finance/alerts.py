"""
/finance/alerts — price, due-date, and budget alerts + check/trigger.
"""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import db_cursor

router = APIRouter(prefix="/finance/alerts", tags=["finance-alerts"])

_NOW = lambda: datetime.now(timezone.utc).isoformat()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    alert_type: Literal["price", "due_date", "budget"]
    # price alerts
    ticker: str | None = None
    threshold: float | None = None
    condition: Literal["above", "below", "percent"] | None = None
    # due_date / budget alerts
    reference_id: int | None = None  # card_id or budget_id
    message: str | None = None


class AlertUpdate(BaseModel):
    threshold: float | None = None
    condition: Literal["above", "below", "percent"] | None = None
    message: str | None = None
    is_active: bool | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_alert_or_404(cur, alert_id: int) -> dict:
    cur.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return dict(row)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
def list_alerts(active_only: bool = True):
    with db_cursor() as cur:
        if active_only:
            cur.execute("SELECT * FROM alerts WHERE is_active = 1 ORDER BY created_at DESC")
        else:
            cur.execute("SELECT * FROM alerts ORDER BY created_at DESC")
        rows = [dict(r) for r in cur.fetchall()]
    return {"alerts": rows, "count": len(rows)}


@router.post("", status_code=201)
def create_alert(payload: AlertCreate):
    if payload.alert_type == "price" and (payload.ticker is None or payload.threshold is None or payload.condition is None):
        raise HTTPException(status_code=400, detail="Price alerts require ticker, threshold, and condition")
    if payload.alert_type in ("due_date", "budget") and payload.reference_id is None:
        raise HTTPException(status_code=400, detail=f"{payload.alert_type} alerts require reference_id")
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO alerts(alert_type, ticker, reference_id, threshold, condition, message, is_active, created_at) "
            "VALUES(?,?,?,?,?,?,1,?)",
            (payload.alert_type, payload.ticker, payload.reference_id,
             payload.threshold, payload.condition, payload.message, _NOW()),
        )
        alert_id = cur.lastrowid
        cur.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        row = dict(cur.fetchone())
    return row


@router.get("/{alert_id}")
def get_alert(alert_id: int):
    with db_cursor() as cur:
        return _get_alert_or_404(cur, alert_id)


@router.put("/{alert_id}")
def update_alert(alert_id: int, payload: AlertUpdate):
    with db_cursor(commit=True) as cur:
        _get_alert_or_404(cur, alert_id)
        if payload.threshold is not None:
            cur.execute("UPDATE alerts SET threshold = ? WHERE id = ?", (payload.threshold, alert_id))
        if payload.condition is not None:
            cur.execute("UPDATE alerts SET condition = ? WHERE id = ?", (payload.condition, alert_id))
        if payload.message is not None:
            cur.execute("UPDATE alerts SET message = ? WHERE id = ?", (payload.message, alert_id))
        if payload.is_active is not None:
            cur.execute("UPDATE alerts SET is_active = ? WHERE id = ?", (1 if payload.is_active else 0, alert_id))
        cur.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        row = dict(cur.fetchone())
    return row


@router.delete("/{alert_id}", status_code=204)
def delete_alert(alert_id: int):
    with db_cursor(commit=True) as cur:
        _get_alert_or_404(cur, alert_id)
        cur.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))


@router.post("/check")
def check_alerts():
    """
    Evaluate all active alerts and mark triggered ones.
    Returns a list of alerts that fired.
    """
    from datetime import date, timedelta

    from backend.services.market_data import get_latest_close

    now = _NOW()
    triggered = []

    with db_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM alerts WHERE is_active = 1")
        active_alerts = [dict(r) for r in cur.fetchall()]

        for alert in active_alerts:
            fired = False
            detail = {}

            if alert["alert_type"] == "price" and alert["ticker"]:
                close, _ = get_latest_close(alert["ticker"])
                if close is not None and alert["threshold"] is not None:
                    if alert["condition"] == "above" and close > alert["threshold"]:
                        fired = True
                        detail = {"price": close, "threshold": alert["threshold"]}
                    elif alert["condition"] == "below" and close < alert["threshold"]:
                        fired = True
                        detail = {"price": close, "threshold": alert["threshold"]}

            elif alert["alert_type"] == "due_date" and alert["reference_id"]:
                cur.execute(
                    "SELECT due_date, name FROM credit_cards WHERE id = ?", (alert["reference_id"],)
                )
                card = cur.fetchone()
                if card and card["due_date"]:
                    days_until = (
                        datetime.fromisoformat(card["due_date"]).date() - date.today()
                    ).days
                    threshold_days = int(alert["threshold"] or 3)
                    if 0 <= days_until <= threshold_days:
                        fired = True
                        detail = {"card": card["name"], "due_date": card["due_date"], "days_until": days_until}

            elif alert["alert_type"] == "budget" and alert["reference_id"]:
                cur.execute("SELECT * FROM budgets WHERE id = ?", (alert["reference_id"],))
                budget = cur.fetchone()
                if budget:
                    month_str = f"{budget['year']}-{budget['month']:02d}"
                    cur.execute(
                        "SELECT COALESCE(SUM(amount),0) as total FROM card_transactions "
                        "WHERE category = ? AND strftime('%Y-%m', transaction_date) = ?",
                        (budget["category"], month_str),
                    )
                    spent_row = cur.fetchone()
                    spent = float(spent_row["total"]) if spent_row else 0.0
                    limit = float(budget["monthly_limit"])
                    pct_threshold = float(alert["threshold"] or 80.0)
                    pct_used = (spent / limit * 100) if limit > 0 else 0
                    if pct_used >= pct_threshold:
                        fired = True
                        detail = {
                            "category": budget["category"],
                            "spent": spent,
                            "limit": limit,
                            "percent_used": round(pct_used, 1),
                        }

            if fired:
                cur.execute(
                    "UPDATE alerts SET triggered_at = ?, is_active = 0 WHERE id = ?",
                    (now, alert["id"]),
                )
                triggered.append({**alert, "triggered_at": now, "detail": detail})

    return {"triggered_count": len(triggered), "triggered": triggered}
