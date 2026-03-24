import logging

from dotenv import load_dotenv

load_dotenv()  # load .env before anything else reads os.getenv

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.auth import verify_api_key
from backend.database import init_db
from backend.routes import events, importers, portfolio, recommendations, reminders, reports
from backend.routes.finance import (
    accounts,
    alerts,
    analyze,
    budget,
    cards,
    goals,
    net_worth,
    report,
    summary,
    trades,
    upload,
)
from backend.routes.finance import portfolio as finance_portfolio
from backend.services.reminder_service import due_reminders

logger = logging.getLogger(__name__)

app = FastAPI(
    title="InvestAssistant",
    version="2.0.0",
    description="Personal finance + investment API for Android client",
    dependencies=[Depends(verify_api_key)],
)

# Allow all origins for Railway/Render + Android app connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = BackgroundScheduler()


@app.on_event("startup")
def on_startup():
    init_db()
    if not scheduler.running:
        scheduler.add_job(
            lambda: due_reminders(),
            "interval",
            minutes=30,
            id="due-reminders",
            replace_existing=True,
        )
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


# ── Legacy routes (kept for backward compatibility) ───────────────────────────
app.include_router(importers.router)
app.include_router(portfolio.router)
app.include_router(events.router)
app.include_router(reports.router)
app.include_router(recommendations.router)
app.include_router(reminders.router)

# ── /finance/* routes ─────────────────────────────────────────────────────────
app.include_router(upload.router)
app.include_router(finance_portfolio.router)
app.include_router(trades.router)
app.include_router(analyze.router)
app.include_router(accounts.router)
app.include_router(cards.router)
app.include_router(budget.router)
app.include_router(goals.router)
app.include_router(alerts.router)
app.include_router(net_worth.router)
app.include_router(summary.router)
app.include_router(report.router)


@app.get("/health", tags=["health"])
def health():
    return {"ok": True, "version": "2.0.0"}
