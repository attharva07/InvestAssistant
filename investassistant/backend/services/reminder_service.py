from datetime import datetime, timezone

from backend.database import db_cursor


def create_reminder(recommendation_id: int, due_at: str, message: str) -> int:
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO reminders(recommendation_id,due_at,message,status) VALUES(?,?,?, 'open')",
            (recommendation_id, due_at, message),
        )
        return cur.lastrowid


def due_reminders() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    with db_cursor() as cur:
        cur.execute("SELECT * FROM reminders WHERE status='open' AND due_at <= ? ORDER BY due_at", (now,))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def resolve_reminder(reminder_id: int, status: str) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE reminders SET status=? WHERE id=?", (status, reminder_id))
        if status == "done":
            cur.execute(
                """
                UPDATE recommendations
                SET status='acted'
                WHERE id=(SELECT recommendation_id FROM reminders WHERE id=?)
                """,
                (reminder_id,),
            )
        elif status == "ignored":
            cur.execute(
                """
                UPDATE recommendations
                SET status='ignored'
                WHERE id=(SELECT recommendation_id FROM reminders WHERE id=?)
                """,
                (reminder_id,),
            )
