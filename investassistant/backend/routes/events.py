import json

from fastapi import APIRouter

from backend.models import ManualEventCreate
from backend.services.portfolio_service import insert_events, rebuild_holdings

router = APIRouter(tags=["events"])


@router.post("/events")
def create_event(payload: ManualEventCreate):
    event = payload.model_dump()
    event["raw_json"] = json.dumps(event)
    inserted = insert_events([event])
    holdings_count = rebuild_holdings()
    return {"inserted": inserted, "holdings_count": holdings_count}
