"""
/finance/summary — full financial picture in one call.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

from backend.database import db_cursor
from backend.services.market_data import get_latest_close
from backend.services.portfolio_service import fetch_holdings

router = APIRouter(prefix="/finance/summary", tags=["finance-summary"])


@router.get("")
def get_summary():
    """
    Aggregate snapshot: portfolio, accounts, credit cards,
    budgets, savings goals, and net worth.
    """
    now = datetime.now(timezone.utc)
    month = now.month
    year = now.year
    month_str = f"{year}-{month:02d}"

    # ── Portfolio ────────────────────────────────────────────────────────────
    holdings = fetch_holdings()
    portfolio_value = 0.0
    total_cost = 0.0
    for h in holdings:
        close, _ = get_latest_close(h["ticker"])
        mv = (close or 0.0) * h["shares"]
        portfolio_value += mv
        total_cost += h["shares"] * h["avg_cost"]
    portfolio_pnl = portfolio_value - total_cost

    with db_cursor() as cur:
        # ── Accounts ────────────────────────────────────────────────────────
        cur.execute("SELECT account_type, COALESCE(SUM(balance),0) as total FROM accounts GROUP BY account_type")
        account_rows = {r["account_type"]: float(r["total"]) for r in cur.fetchall()}
        total_account_balance = sum(account_rows.values())

        # ── Credit Cards ────────────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(current_balance),0) as bal, "
                    "COALESCE(SUM(minimum_payment),0) as min_pay FROM credit_cards")
        card_row = cur.fetchone()
        card_count = card_row["cnt"]
        card_balance = float(card_row["bal"])
        min_payment = float(card_row["min_pay"])

        # ── Budgets: current month ───────────────────────────────────────────
        cur.execute("SELECT * FROM budgets WHERE month = ? AND year = ?", (month, year))
        budgets = [dict(r) for r in cur.fetchall()]
        budget_summary = []
        total_budget_limit = 0.0
        total_budget_spent = 0.0
        for b in budgets:
            cur.execute(
                "SELECT COALESCE(SUM(amount),0) as total FROM card_transactions "
                "WHERE category = ? AND strftime('%Y-%m', transaction_date) = ?",
                (b["category"], month_str),
            )
            spent = float(cur.fetchone()["total"])
            budget_summary.append({
                "category": b["category"],
                "limit": b["monthly_limit"],
                "spent": round(spent, 2),
                "over_budget": spent > b["monthly_limit"],
            })
            total_budget_limit += b["monthly_limit"]
            total_budget_spent += spent

        # ── Savings Goals ────────────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(current_amount),0) as saved, "
                    "COALESCE(SUM(target_amount),0) as target FROM savings_goals")
        goals_row = cur.fetchone()
        goals_count = goals_row["cnt"]
        goals_saved = float(goals_row["saved"])
        goals_target = float(goals_row["target"])

        # ── Active Alerts ────────────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) as cnt FROM alerts WHERE is_active = 1")
        active_alerts = cur.fetchone()["cnt"]

    total_assets = round(portfolio_value + total_account_balance, 2)
    total_liabilities = round(card_balance, 2)
    net_worth = round(total_assets - total_liabilities, 2)

    return {
        "as_of": now.isoformat(),
        "portfolio": {
            "holdings_count": len(holdings),
            "total_value": round(portfolio_value, 2),
            "total_cost": round(total_cost, 2),
            "unrealized_pnl": round(portfolio_pnl, 2),
            "unrealized_pnl_pct": round((portfolio_pnl / total_cost) * 100, 2) if total_cost else None,
        },
        "accounts": {
            "by_type": account_rows,
            "total_balance": round(total_account_balance, 2),
        },
        "credit_cards": {
            "count": card_count,
            "total_balance": round(card_balance, 2),
            "total_minimum_payment": round(min_payment, 2),
        },
        "budget": {
            "month": month,
            "year": year,
            "categories": budget_summary,
            "total_limit": round(total_budget_limit, 2),
            "total_spent": round(total_budget_spent, 2),
        },
        "savings_goals": {
            "count": goals_count,
            "total_saved": round(goals_saved, 2),
            "total_target": round(goals_target, 2),
            "overall_progress_pct": round((goals_saved / goals_target) * 100, 1) if goals_target else None,
        },
        "alerts": {
            "active_count": active_alerts,
        },
        "net_worth": {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "net_worth": net_worth,
        },
    }
