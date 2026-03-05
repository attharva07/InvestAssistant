from datetime import datetime, timedelta

from fastapi import APIRouter

from backend.routes.reports import daily_report
from backend.services.recommendation_service import create_recommendation
from backend.services.reminder_service import create_reminder

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/generate")
def generate_recommendations():
    report = daily_report()
    created = []
    for row in report["rows"]:
        reasons = []
        action = "HOLD"
        confidence = 0.55
        rsi = row["rsi_14"]
        drawdown = row["drawdown_6mo_pct"]
        if rsi is not None and rsi < 35 and (drawdown is not None and drawdown < -8):
            action = "ADD"
            confidence = 0.72
            reasons = ["RSI indicates weak momentum", "Price trades below 6mo highs"]
        elif rsi is not None and rsi > 70:
            action = "PAUSE"
            confidence = 0.7
            reasons = ["Overbought RSI"]
        elif "volatility_spike" in row["risk_flags"]:
            action = "WATCH"
            confidence = 0.6
            reasons = ["Recent volatility spike"]
        else:
            reasons = ["No strong setup; maintain existing stance"]

        rec_id = create_recommendation(row["ticker"], action, confidence, reasons, follow_up_days=3)
        follow_up_at = (datetime.utcnow() + timedelta(days=3)).isoformat() + "Z"
        msg = f"You asked me to watch {row['ticker']}, it's moved since the signal. Did you act?"
        reminder_id = create_reminder(rec_id, follow_up_at, msg)
        created.append({"recommendation_id": rec_id, "reminder_id": reminder_id, "ticker": row["ticker"], "action": action})

    return {"created": created, "count": len(created)}
