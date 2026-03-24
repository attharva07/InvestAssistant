"""
/finance/accounts — checking and savings accounts CRUD + transactions.
"""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import db_cursor

router = APIRouter(prefix="/finance/accounts", tags=["finance-accounts"])

_NOW = lambda: datetime.now(timezone.utc).isoformat()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    name: str
    account_type: Literal["checking", "savings"]
    balance: float = 0.0
    institution: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    balance: float | None = None
    institution: str | None = None


class AccountTransactionCreate(BaseModel):
    amount: float
    description: str | None = None
    transaction_type: Literal["credit", "debit"]
    transaction_date: str  # ISO date e.g. "2024-01-15"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_account_or_404(cur, account_id: int) -> dict:
    cur.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return dict(row)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
def list_accounts():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM accounts ORDER BY name")
        rows = [dict(r) for r in cur.fetchall()]
    total_balance = sum(r["balance"] for r in rows)
    return {"accounts": rows, "total_balance": round(total_balance, 2)}


@router.post("", status_code=201)
def create_account(payload: AccountCreate):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO accounts(name, account_type, balance, institution, created_at) VALUES(?,?,?,?,?)",
            (payload.name, payload.account_type, payload.balance, payload.institution, _NOW()),
        )
        account_id = cur.lastrowid
        cur.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = dict(cur.fetchone())
    return row


@router.get("/{account_id}")
def get_account(account_id: int):
    with db_cursor() as cur:
        return _get_account_or_404(cur, account_id)


@router.put("/{account_id}")
def update_account(account_id: int, payload: AccountUpdate):
    with db_cursor(commit=True) as cur:
        _get_account_or_404(cur, account_id)
        if payload.name is not None:
            cur.execute("UPDATE accounts SET name = ? WHERE id = ?", (payload.name, account_id))
        if payload.balance is not None:
            cur.execute("UPDATE accounts SET balance = ? WHERE id = ?", (payload.balance, account_id))
        if payload.institution is not None:
            cur.execute("UPDATE accounts SET institution = ? WHERE id = ?", (payload.institution, account_id))
        cur.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = dict(cur.fetchone())
    return row


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int):
    with db_cursor(commit=True) as cur:
        _get_account_or_404(cur, account_id)
        cur.execute("DELETE FROM account_transactions WHERE account_id = ?", (account_id,))
        cur.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


@router.get("/{account_id}/transactions")
def list_account_transactions(
    account_id: int,
    limit: int = Query(default=100, le=500),
):
    with db_cursor() as cur:
        _get_account_or_404(cur, account_id)
        cur.execute(
            "SELECT * FROM account_transactions WHERE account_id = ? ORDER BY transaction_date DESC LIMIT ?",
            (account_id, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"account_id": account_id, "transactions": rows, "count": len(rows)}


@router.post("/{account_id}/transactions", status_code=201)
def add_account_transaction(account_id: int, payload: AccountTransactionCreate):
    with db_cursor(commit=True) as cur:
        acct = _get_account_or_404(cur, account_id)
        now = _NOW()
        cur.execute(
            "INSERT INTO account_transactions(account_id, amount, description, transaction_type, transaction_date, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (account_id, payload.amount, payload.description, payload.transaction_type, payload.transaction_date, now),
        )
        txn_id = cur.lastrowid
        # Update running balance
        delta = payload.amount if payload.transaction_type == "credit" else -payload.amount
        new_balance = round(acct["balance"] + delta, 4)
        cur.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, account_id))
        cur.execute("SELECT * FROM account_transactions WHERE id = ?", (txn_id,))
        txn = dict(cur.fetchone())
    return {"transaction": txn, "new_balance": new_balance}
