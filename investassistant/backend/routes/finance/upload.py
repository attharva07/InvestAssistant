"""
/finance/upload — CSV seed upload and monthly reconciliation.
"""
import io

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.services.portfolio_service import fetch_holdings, insert_events, rebuild_holdings
from backend.services.robinhood_import import MappingError, parse_csv_text

router = APIRouter(prefix="/finance/upload", tags=["finance-upload"])


@router.post("")
async def upload_csv(file: UploadFile = File(...)):
    """Upload a Robinhood (or compatible) CSV to seed the transaction log."""
    try:
        text = (await file.read()).decode("utf-8-sig")
        events, mapping, stats = parse_csv_text(text)
    except MappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

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
    return {
        "imported_events": imported,
        "skipped_count": stats["skipped_count"],
        "errors_sample": stats["errors_sample"],
        "holdings_count": holdings_count,
        "detected_columns": mapping,
    }


@router.post("/reconcile")
async def reconcile_csv(file: UploadFile = File(...)):
    """
    Monthly reconciliation: compare uploaded CSV against the existing manual log.
    Returns rows present in the CSV but not yet in the database (candidates to import).
    """
    try:
        text = (await file.read()).decode("utf-8-sig")
        events, mapping, stats = parse_csv_text(text, source="reconcile_csv")
    except MappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Build a set of (ticker, event_ts, event_type) tuples already in the DB
    from backend.database import db_cursor

    with db_cursor() as cur:
        cur.execute("SELECT ticker, event_ts, event_type FROM events")
        existing = {(r["ticker"], r["event_ts"][:10], r["event_type"]) for r in cur.fetchall()}

    new_rows = []
    already_recorded = 0
    for e in events:
        key = (e.ticker, (e.event_ts or "")[:10], e.event_type)
        if key in existing:
            already_recorded += 1
        else:
            new_rows.append(
                {
                    "ticker": e.ticker,
                    "event_type": e.event_type,
                    "event_ts": e.event_ts,
                    "quantity": e.quantity,
                    "price": e.price,
                    "amount": e.amount,
                    "description": e.description,
                }
            )

    return {
        "csv_row_count": len(events),
        "already_recorded": already_recorded,
        "new_rows_count": len(new_rows),
        "new_rows": new_rows,
        "skipped_count": stats["skipped_count"],
        "detected_columns": mapping,
    }
