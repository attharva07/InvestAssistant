"""
/finance/portfolio — live holdings with P&L.
"""
from fastapi import APIRouter

from backend.services.market_data import get_latest_close
from backend.services.portfolio_service import fetch_holdings

router = APIRouter(prefix="/finance/portfolio", tags=["finance-portfolio"])


@router.get("")
def get_portfolio():
    """Return all current holdings with live price, market value, and unrealized P&L."""
    holdings = fetch_holdings()
    total_value = 0.0
    total_cost = 0.0
    delayed_any = False

    for h in holdings:
        close, delayed = get_latest_close(h["ticker"])
        h["last_close"] = close
        h["market_value"] = (close or 0.0) * h["shares"]
        cost_basis = h["shares"] * h["avg_cost"]
        h["cost_basis"] = round(cost_basis, 4)
        h["unrealized_pnl"] = round(h["market_value"] - cost_basis, 4)
        h["unrealized_pnl_pct"] = (
            round((h["unrealized_pnl"] / cost_basis) * 100, 2) if cost_basis else None
        )
        total_value += h["market_value"]
        total_cost += cost_basis
        delayed_any = delayed_any or delayed

    total_pnl = total_value - total_cost
    return {
        "holdings": holdings,
        "total_value_usd": round(total_value, 2),
        "total_cost_usd": round(total_cost, 2),
        "total_unrealized_pnl": round(total_pnl, 2),
        "total_unrealized_pnl_pct": round((total_pnl / total_cost) * 100, 2) if total_cost else None,
        "data_delayed": delayed_any,
    }
