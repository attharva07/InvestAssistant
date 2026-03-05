from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from backend.database import init_db
from backend.routes import events, importers, portfolio, recommendations, reminders, reports
from backend.services.reminder_service import due_reminders

app = FastAPI(title="InvestAssistant", version="0.1.0")
scheduler = BackgroundScheduler()


@app.on_event("startup")
def on_startup():
    init_db()
    if not scheduler.running:
        scheduler.add_job(lambda: due_reminders(), "interval", minutes=30, id="due-reminders", replace_existing=True)
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


app.include_router(importers.router)
app.include_router(portfolio.router)
app.include_router(events.router)
app.include_router(reports.router)
app.include_router(recommendations.router)
app.include_router(reminders.router)


@app.get("/health")
def health():
    return {"ok": True}
