"""
/finance/budget — category spending limits + monthly actual vs budget.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import db_cursor

router = APIRouter(prefix="/finance/budget", tags=["finance-budget"])

_NOW = lambda: datetime.now(timezone.utc).isoformat()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    category: str
    monthly_limit: float
    month: int  # 1-12
    year: int


class BudgetUpdate(BaseModel):
    monthly_limit: float | None = None
    category: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_budget_or_404(cur, budget_id: int) -> dict:
    cur.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Budget {budget_id} not found")
    return dict(row)


def _spending_for_month(cur, category: str, month: int, year: int) -> float:
    """Sum card_transactions for a category in the given month/year."""
    month_str = f"{year}-{month:02d}"
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM card_transactions "
        "WHERE category = ? AND strftime('%Y-%m', transaction_date) = ?",
        (category, month_str),
    )
    row = cur.fetchone()
    return float(row["total"]) if row else 0.0


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
def list_budgets(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None),
):
    """List all budgets, optionally filtered by month/year."""
    now = datetime.now(timezone.utc)
    m = month or now.month
    y = year or now.year
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM budgets WHERE month = ? AND year = ? ORDER BY category",
            (m, y),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"month": m, "year": y, "budgets": rows}


@router.post("", status_code=201)
def create_budget(payload: BudgetCreate):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO budgets(category, monthly_limit, month, year, created_at) VALUES(?,?,?,?,?)",
            (payload.category, payload.monthly_limit, payload.month, payload.year, _NOW()),
        )
        budget_id = cur.lastrowid
        cur.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,))
        row = dict(cur.fetchone())
    return row


@router.get("/spending")
def budget_vs_actual(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None),
):
    """Return each budget category with limit, actual spend, and remaining."""
    now = datetime.now(timezone.utc)
    m = month or now.month
    y = year or now.year
    with db_cursor() as cur:
        cur.execute("SELECT * FROM budgets WHERE month = ? AND year = ?", (m, y))
        budgets = [dict(r) for r in cur.fetchall()]
        result = []
        for b in budgets:
            spent = _spending_for_month(cur, b["category"], m, y)
            remaining = round(b["monthly_limit"] - spent, 2)
            pct_used = round((spent / b["monthly_limit"]) * 100, 1) if b["monthly_limit"] else None
            result.append(
                {
                    "budget_id": b["id"],
                    "category": b["category"],
                    "monthly_limit": b["monthly_limit"],
                    "spent": round(spent, 2),
                    "remaining": remaining,
                    "percent_used": pct_used,
                    "over_budget": remaining < 0,
                }
            )
    total_limit = sum(r["monthly_limit"] for r in result)
    total_spent = sum(r["spent"] for r in result)
    return {
        "month": m,
        "year": y,
        "categories": result,
        "total_limit": round(total_limit, 2),
        "total_spent": round(total_spent, 2),
        "total_remaining": round(total_limit - total_spent, 2),
    }


@router.get("/{budget_id}")
def get_budget(budget_id: int):
    with db_cursor() as cur:
        return _get_budget_or_404(cur, budget_id)


@router.put("/{budget_id}")
def update_budget(budget_id: int, payload: BudgetUpdate):
    with db_cursor(commit=True) as cur:
        _get_budget_or_404(cur, budget_id)
        if payload.monthly_limit is not None:
            cur.execute("UPDATE budgets SET monthly_limit = ? WHERE id = ?", (payload.monthly_limit, budget_id))
        if payload.category is not None:
            cur.execute("UPDATE budgets SET category = ? WHERE id = ?", (payload.category, budget_id))
        cur.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,))
        row = dict(cur.fetchone())
    return row


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: int):
    with db_cursor(commit=True) as cur:
        _get_budget_or_404(cur, budget_id)
        cur.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
