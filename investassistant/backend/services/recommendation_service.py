import json
from datetime import datetime, timedelta, timezone

from backend.database import db_cursor


def create_recommendation(ticker: str, action: str, confidence: float, reasons: list[str], follow_up_days: int = 3) -> int:
    now = datetime.now(timezone.utc)
    follow_up = now + timedelta(days=follow_up_days)
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO recommendations(ticker,action,confidence,reasons_json,created_at,follow_up_at,status)
            VALUES(?,?,?,?,?,?, 'open')
            """,
            (ticker, action, confidence, json.dumps(reasons), now.isoformat(), follow_up.isoformat()),
        )
        return cur.lastrowid


def list_recommendations(status: str = "open") -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM recommendations WHERE status=? ORDER BY created_at DESC", (status,))
        rows = cur.fetchall()
    recs = []
    for row in rows:
        rec = dict(row)
        rec["reasons"] = json.loads(rec.pop("reasons_json"))
        recs.append(rec)
    return recs
