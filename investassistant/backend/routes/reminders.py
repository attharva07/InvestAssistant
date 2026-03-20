from fastapi import APIRouter, HTTPException

from backend.models import ResolveReminderRequest
from backend.services.portfolio_service import insert_events, rebuild_holdings
from backend.services.reminder_service import due_reminders, resolve_reminder

router = APIRouter(tags=["reminders"])


@router.get("/reminders")
def get_reminders():
    return {"items": due_reminders()}


@router.post("/reminders/{reminder_id}/resolve")
def resolve(reminder_id: int, payload: ResolveReminderRequest):
    if payload.status not in {"done", "ignored"}:
        raise HTTPException(status_code=400, detail="status must be done or ignored")
    resolve_reminder(reminder_id, payload.status)

    if payload.status == "done" and payload.acted_event:
        import json
        event = payload.acted_event.model_dump()
        event["raw_json"] = json.dumps(event, default=str)
        insert_events([event])
        rebuild_holdings()
    return {"status": payload.status}
