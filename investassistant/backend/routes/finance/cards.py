"""
/finance/cards — credit card CRUD + transactions + due dates.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import db_cursor

router = APIRouter(prefix="/finance/cards", tags=["finance-cards"])

_NOW = lambda: datetime.now(timezone.utc).isoformat()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CardCreate(BaseModel):
    name: str
    institution: str | None = None
    credit_limit: float = 0.0
    current_balance: float = 0.0
    due_date: str | None = None   # ISO date e.g. "2024-02-01"
    minimum_payment: float | None = None


class CardUpdate(BaseModel):
    name: str | None = None
    institution: str | None = None
    credit_limit: float | None = None
    current_balance: float | None = None
    due_date: str | None = None
    minimum_payment: float | None = None


class CardTransactionCreate(BaseModel):
    amount: float
    description: str | None = None
    category: str | None = None
    transaction_date: str  # ISO date


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_card_or_404(cur, card_id: int) -> dict:
    cur.execute("SELECT * FROM credit_cards WHERE id = ?", (card_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found")
    return dict(row)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
def list_cards():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM credit_cards ORDER BY name")
        rows = [dict(r) for r in cur.fetchall()]
    total_balance = sum(r["current_balance"] for r in rows)
    total_min = sum(r["minimum_payment"] or 0.0 for r in rows)
    return {
        "cards": rows,
        "total_balance": round(total_balance, 2),
        "total_minimum_payment": round(total_min, 2),
    }


@router.post("", status_code=201)
def create_card(payload: CardCreate):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO credit_cards(name, institution, credit_limit, current_balance, due_date, minimum_payment, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (payload.name, payload.institution, payload.credit_limit, payload.current_balance,
             payload.due_date, payload.minimum_payment, _NOW()),
        )
        card_id = cur.lastrowid
        cur.execute("SELECT * FROM credit_cards WHERE id = ?", (card_id,))
        row = dict(cur.fetchone())
    return row


@router.get("/due")
def cards_due_soon(days_ahead: int = Query(default=7, ge=1, le=60)):
    """Return cards with due dates within the next N days."""
    from datetime import date, timedelta
    today = date.today()
    cutoff = (today + timedelta(days=days_ahead)).isoformat()
    today_str = today.isoformat()
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM credit_cards WHERE due_date IS NOT NULL AND due_date >= ? AND due_date <= ? ORDER BY due_date",
            (today_str, cutoff),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"days_ahead": days_ahead, "cards_due": rows}


@router.get("/{card_id}")
def get_card(card_id: int):
    with db_cursor() as cur:
        return _get_card_or_404(cur, card_id)


@router.put("/{card_id}")
def update_card(card_id: int, payload: CardUpdate):
    updates = payload.model_dump(exclude_none=True)
    with db_cursor(commit=True) as cur:
        _get_card_or_404(cur, card_id)
        for field, value in updates.items():
            cur.execute(f"UPDATE credit_cards SET {field} = ? WHERE id = ?", (value, card_id))
        cur.execute("SELECT * FROM credit_cards WHERE id = ?", (card_id,))
        row = dict(cur.fetchone())
    return row


@router.delete("/{card_id}", status_code=204)
def delete_card(card_id: int):
    with db_cursor(commit=True) as cur:
        _get_card_or_404(cur, card_id)
        cur.execute("DELETE FROM card_transactions WHERE card_id = ?", (card_id,))
        cur.execute("DELETE FROM credit_cards WHERE id = ?", (card_id,))


@router.get("/{card_id}/transactions")
def list_card_transactions(
    card_id: int,
    limit: int = Query(default=100, le=500),
):
    with db_cursor() as cur:
        _get_card_or_404(cur, card_id)
        cur.execute(
            "SELECT * FROM card_transactions WHERE card_id = ? ORDER BY transaction_date DESC LIMIT ?",
            (card_id, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"card_id": card_id, "transactions": rows, "count": len(rows)}


@router.post("/{card_id}/transactions", status_code=201)
def add_card_transaction(card_id: int, payload: CardTransactionCreate):
    with db_cursor(commit=True) as cur:
        card = _get_card_or_404(cur, card_id)
        now = _NOW()
        cur.execute(
            "INSERT INTO card_transactions(card_id, amount, description, category, transaction_date, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (card_id, payload.amount, payload.description, payload.category, payload.transaction_date, now),
        )
        txn_id = cur.lastrowid
        new_balance = round(card["current_balance"] + payload.amount, 4)
        cur.execute("UPDATE credit_cards SET current_balance = ? WHERE id = ?", (new_balance, card_id))
        cur.execute("SELECT * FROM card_transactions WHERE id = ?", (txn_id,))
        txn = dict(cur.fetchone())
    return {"transaction": txn, "new_balance": new_balance}
