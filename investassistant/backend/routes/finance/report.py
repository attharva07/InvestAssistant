"""
/finance/report — monthly financial report.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from backend.database import db_cursor
from backend.services.indicators import compute_rsi_14, drawdown_from_high
from backend.services.market_data import get_history, get_latest_close
from backend.services.portfolio_service import fetch_holdings

router = APIRouter(prefix="/finance/report", tags=["finance-report"])


def _build_report(month: int, year: int) -> dict:
    month_str = f"{year}-{month:02d}"
    now = datetime.now(timezone.utc).isoformat()

    with db_cursor() as cur:
        # ── Portfolio performance ────────────────────────────────────────────
        holdings = fetch_holdings()
        portfolio_rows = []
        total_value = 0.0
        total_cost = 0.0
        for h in holdings:
            close, delayed = get_latest_close(h["ticker"])
            mv = (close or 0.0) * h["shares"]
            cost = h["shares"] * h["avg_cost"]
            total_value += mv
            total_cost += cost
            portfolio_rows.append({
                "ticker": h["ticker"],
                "shares": h["shares"],
                "avg_cost": h["avg_cost"],
                "current_price": close,
                "market_value": round(mv, 2),
                "unrealized_pnl": round(mv - cost, 2),
                "data_delayed": delayed,
            })

        # ── Trades this month ────────────────────────────────────────────────
        cur.execute(
            "SELECT event_type, ticker, quantity, price, amount, event_ts FROM events "
            "WHERE event_type IN ('BUY','SELL') AND strftime('%Y-%m', event_ts) = ? "
            "ORDER BY event_ts",
            (month_str,),
        )
        trades_this_month = [dict(r) for r in cur.fetchall()]

        # ── Account activity ─────────────────────────────────────────────────
        cur.execute(
            "SELECT a.name, a.account_type, "
            "COALESCE(SUM(CASE WHEN t.transaction_type='credit' THEN t.amount ELSE 0 END),0) as credits, "
            "COALESCE(SUM(CASE WHEN t.transaction_type='debit' THEN t.amount ELSE 0 END),0) as debits "
            "FROM accounts a "
            "LEFT JOIN account_transactions t ON t.account_id = a.id AND strftime('%Y-%m', t.transaction_date) = ? "
            "GROUP BY a.id",
            (month_str,),
        )
        account_activity = [dict(r) for r in cur.fetchall()]

        # ── Card spending by category ────────────────────────────────────────
        cur.execute(
            "SELECT COALESCE(category, 'Uncategorized') as category, SUM(amount) as total "
            "FROM card_transactions WHERE strftime('%Y-%m', transaction_date) = ? "
            "GROUP BY category ORDER BY total DESC",
            (month_str,),
        )
        spending_by_category = [dict(r) for r in cur.fetchall()]
        total_card_spending = sum(r["total"] for r in spending_by_category)

        # ── Budget vs actual ────────────────────────────────────────────────
        cur.execute("SELECT * FROM budgets WHERE month = ? AND year = ?", (month, year))
        budgets = [dict(r) for r in cur.fetchall()]
        budget_rows = []
        for b in budgets:
            cur.execute(
                "SELECT COALESCE(SUM(amount),0) as total FROM card_transactions "
                "WHERE category = ? AND strftime('%Y-%m', transaction_date) = ?",
                (b["category"], month_str),
            )
            spent = float(cur.fetchone()["total"])
            budget_rows.append({
                "category": b["category"],
                "limit": b["monthly_limit"],
                "spent": round(spent, 2),
                "remaining": round(b["monthly_limit"] - spent, 2),
                "over_budget": spent > b["monthly_limit"],
            })

        # ── Savings goals progress ───────────────────────────────────────────
        cur.execute("SELECT * FROM savings_goals ORDER BY name")
        goals = []
        for g in cur.fetchall():
            g = dict(g)
            pct = round((g["current_amount"] / g["target_amount"]) * 100, 1) if g["target_amount"] else 0
            goals.append({
                "name": g["name"],
                "target": g["target_amount"],
                "saved": g["current_amount"],
                "progress_pct": pct,
                "target_date": g["target_date"],
            })

        # ── Alerts triggered this month ─────────────────────────────────────
        cur.execute(
            "SELECT * FROM alerts WHERE triggered_at IS NOT NULL AND strftime('%Y-%m', triggered_at) = ?",
            (month_str,),
        )
        triggered_alerts = [dict(r) for r in cur.fetchall()]

        # ── Top movers ──────────────────────────────────────────────────────
        movers = []
        for h in holdings[:10]:  # limit to first 10 tickers for perf
            hist, _ = get_history(h["ticker"], "1mo")
            if not hist.empty and len(hist) >= 2:
                start = float(hist["Close"].iloc[0])
                end = float(hist["Close"].iloc[-1])
                pct = round(((end - start) / start) * 100, 2) if start else None
                movers.append({"ticker": h["ticker"], "change_1mo_pct": pct})
        movers.sort(key=lambda x: abs(x["change_1mo_pct"] or 0), reverse=True)

    return {
        "report_month": month,
        "report_year": year,
        "generated_at": now,
        "portfolio": {
            "holdings": portfolio_rows,
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_unrealized_pnl": round(total_value - total_cost, 2),
            "trades_this_month": trades_this_month,
            "trade_count": len(trades_this_month),
            "top_movers": movers[:5],
        },
        "accounts": {
            "activity": account_activity,
        },
        "credit_cards": {
            "spending_by_category": spending_by_category,
            "total_spending": round(total_card_spending, 2),
        },
        "budget": {
            "categories": budget_rows,
        },
        "savings_goals": goals,
        "alerts_triggered": triggered_alerts,
        "alert_count": len(triggered_alerts),
    }


@router.get("")
def monthly_report(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None),
):
    """Generate the monthly financial report (defaults to current month)."""
    now = datetime.now(timezone.utc)
    m = month or now.month
    y = year or now.year
    return _build_report(m, y)


@router.get("/{year}/{month}")
def monthly_report_by_date(year: int, month: int):
    """Generate the monthly financial report for a specific year/month."""
    if month < 1 or month > 12:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Month must be 1-12")
    return _build_report(month, year)
