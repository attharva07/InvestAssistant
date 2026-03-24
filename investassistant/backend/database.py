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

            CREATE TABLE IF NOT EXISTS accounts(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              account_type TEXT NOT NULL CHECK(account_type IN ('checking','savings')),
              balance REAL NOT NULL DEFAULT 0.0,
              institution TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS account_transactions(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              account_id INTEGER NOT NULL,
              amount REAL NOT NULL,
              description TEXT,
              transaction_type TEXT NOT NULL CHECK(transaction_type IN ('credit','debit')),
              transaction_date TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS credit_cards(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              institution TEXT,
              credit_limit REAL NOT NULL DEFAULT 0.0,
              current_balance REAL NOT NULL DEFAULT 0.0,
              due_date TEXT,
              minimum_payment REAL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS card_transactions(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              card_id INTEGER NOT NULL,
              amount REAL NOT NULL,
              description TEXT,
              category TEXT,
              transaction_date TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(card_id) REFERENCES credit_cards(id)
            );

            CREATE TABLE IF NOT EXISTS budgets(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              category TEXT NOT NULL,
              monthly_limit REAL NOT NULL,
              month INTEGER NOT NULL,
              year INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS savings_goals(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              target_amount REAL NOT NULL,
              current_amount REAL NOT NULL DEFAULT 0.0,
              target_date TEXT,
              description TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              alert_type TEXT NOT NULL CHECK(alert_type IN ('price','due_date','budget')),
              ticker TEXT,
              reference_id INTEGER,
              threshold REAL,
              condition TEXT CHECK(condition IN ('above','below','percent')),
              message TEXT,
              is_active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              triggered_at TEXT
            );

            CREATE TABLE IF NOT EXISTS net_worth_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              total_assets REAL NOT NULL,
              total_liabilities REAL NOT NULL,
              net_worth REAL NOT NULL,
              snapshot_date TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
    finally:
        conn.close()
