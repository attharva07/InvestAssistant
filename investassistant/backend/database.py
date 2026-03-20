import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "investassistant.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def db_cursor(commit: bool = False):
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    finally:
        cur.close()
        conn.close()


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY,
              source TEXT NOT NULL,
              event_type TEXT NOT NULL,
              ticker TEXT,
              quantity REAL,
              price REAL,
              amount REAL,
              currency TEXT DEFAULT 'USD',
              event_ts TEXT NOT NULL,
              description TEXT,
              raw_json TEXT,
              recommendation_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS holdings(
              ticker TEXT PRIMARY KEY,
              shares REAL NOT NULL,
              avg_cost REAL NOT NULL,
              last_updated TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_cache(
              ticker TEXT NOT NULL,
              as_of_date TEXT NOT NULL,
              close REAL NOT NULL,
              retrieved_at TEXT NOT NULL,
              PRIMARY KEY (ticker, as_of_date)
            );

            CREATE TABLE IF NOT EXISTS recommendations(
              id INTEGER PRIMARY KEY,
              ticker TEXT NOT NULL,
              action TEXT NOT NULL,
              confidence REAL NOT NULL,
              reasons_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              follow_up_at TEXT,
              status TEXT NOT NULL DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS reminders(
              id INTEGER PRIMARY KEY,
              recommendation_id INTEGER NOT NULL,
              due_at TEXT NOT NULL,
              message TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'open',
              FOREIGN KEY(recommendation_id) REFERENCES recommendations(id)
            );

            CREATE TABLE IF NOT EXISTS preferences(
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
    finally:
        conn.close()
