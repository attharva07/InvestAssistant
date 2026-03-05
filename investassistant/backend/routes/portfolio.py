from fastapi import APIRouter

from backend.services.market_data import get_latest_close
from backend.services.portfolio_service import fetch_holdings

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio")
def get_portfolio():
    holdings = fetch_holdings()
    total = 0.0
    delayed_any = False
    for h in holdings:
        close, delayed = get_latest_close(h["ticker"])
        h["last_close"] = close
        h["market_value"] = (close or 0.0) * h["shares"]
        h["unrealized_pnl"] = h["market_value"] - (h["shares"] * h["avg_cost"])
        total += h["market_value"]
        delayed_any = delayed_any or delayed
    return {"holdings": holdings, "total_value_usd": total, "data_delayed": delayed_any}
