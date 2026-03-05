from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from backend.services.portfolio_service import insert_events, rebuild_holdings
from backend.services.robinhood_import import MappingError, load_and_parse_csv, parse_csv_text

router = APIRouter(prefix="/import", tags=["import"])
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@router.post("/robinhood")
async def import_robinhood(request: Request, file: UploadFile | None = File(default=None)):
    try:
        if file is not None:
            text = (await file.read()).decode("utf-8-sig")
            events, mapping = parse_csv_text(text)
        else:
            payload = await request.json()
            filename = payload.get("filename")
            if not filename:
                raise HTTPException(status_code=400, detail="filename is required when upload file is not provided")
            path = (DATA_DIR / filename).resolve()
            if DATA_DIR not in path.parents and path != DATA_DIR:
                raise HTTPException(status_code=400, detail="Invalid file path")
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"File not found: {filename}")
            events, mapping = load_and_parse_csv(str(path))

        records = [
            {
                "source": e.source,
                "event_type": e.event_type,
                "ticker": e.ticker,
                "quantity": e.quantity,
                "price": e.price,
                "amount": e.amount,
                "currency": e.currency,
                "event_ts": e.event_ts,
                "description": e.description,
                "raw_json": e.raw_json,
                "recommendation_id": None,
            }
            for e in events
        ]
        imported = insert_events(records)
        holdings_count = rebuild_holdings()
        return {"imported_events": imported, "holdings_count": holdings_count, "detected_columns": mapping}
    except MappingError as e:
        raise HTTPException(status_code=422, detail=str(e))
