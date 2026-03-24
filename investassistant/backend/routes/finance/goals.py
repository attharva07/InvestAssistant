"""
/finance/goals — savings goals + progress tracking.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import db_cursor

router = APIRouter(prefix="/finance/goals", tags=["finance-goals"])

_NOW = lambda: datetime.now(timezone.utc).isoformat()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class GoalCreate(BaseModel):
    name: str
    target_amount: float
    current_amount: float = 0.0
    target_date: str | None = None  # ISO date e.g. "2025-12-31"
    description: str | None = None


class GoalUpdate(BaseModel):
    name: str | None = None
    target_amount: float | None = None
    target_date: str | None = None
    description: str | None = None


class GoalDeposit(BaseModel):
    amount: float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_goal_or_404(cur, goal_id: int) -> dict:
    cur.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")
    return dict(row)


def _enrich(goal: dict) -> dict:
    pct = round((goal["current_amount"] / goal["target_amount"]) * 100, 1) if goal["target_amount"] else 0.0
    remaining = round(goal["target_amount"] - goal["current_amount"], 2)
    goal["progress_pct"] = pct
    goal["remaining_amount"] = remaining
    goal["achieved"] = goal["current_amount"] >= goal["target_amount"]
    return goal


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
def list_goals():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM savings_goals ORDER BY name")
        rows = [_enrich(dict(r)) for r in cur.fetchall()]
    return {"goals": rows, "count": len(rows)}


@router.post("", status_code=201)
def create_goal(payload: GoalCreate):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO savings_goals(name, target_amount, current_amount, target_date, description, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (payload.name, payload.target_amount, payload.current_amount,
             payload.target_date, payload.description, _NOW()),
        )
        goal_id = cur.lastrowid
        cur.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        row = _enrich(dict(cur.fetchone()))
    return row


@router.get("/{goal_id}")
def get_goal(goal_id: int):
    with db_cursor() as cur:
        return _enrich(_get_goal_or_404(cur, goal_id))


@router.put("/{goal_id}")
def update_goal(goal_id: int, payload: GoalUpdate):
    with db_cursor(commit=True) as cur:
        _get_goal_or_404(cur, goal_id)
        if payload.name is not None:
            cur.execute("UPDATE savings_goals SET name = ? WHERE id = ?", (payload.name, goal_id))
        if payload.target_amount is not None:
            cur.execute("UPDATE savings_goals SET target_amount = ? WHERE id = ?", (payload.target_amount, goal_id))
        if payload.target_date is not None:
            cur.execute("UPDATE savings_goals SET target_date = ? WHERE id = ?", (payload.target_date, goal_id))
        if payload.description is not None:
            cur.execute("UPDATE savings_goals SET description = ? WHERE id = ?", (payload.description, goal_id))
        cur.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        row = _enrich(dict(cur.fetchone()))
    return row


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int):
    with db_cursor(commit=True) as cur:
        _get_goal_or_404(cur, goal_id)
        cur.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))


@router.post("/{goal_id}/deposit")
def deposit_to_goal(goal_id: int, payload: GoalDeposit):
    """Add funds toward a savings goal."""
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be positive")
    with db_cursor(commit=True) as cur:
        goal = _get_goal_or_404(cur, goal_id)
        new_amount = round(goal["current_amount"] + payload.amount, 4)
        cur.execute("UPDATE savings_goals SET current_amount = ? WHERE id = ?", (new_amount, goal_id))
        cur.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        row = _enrich(dict(cur.fetchone()))
    return row
