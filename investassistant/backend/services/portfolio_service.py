from collections import defaultdict
from datetime import datetime

from backend.database import db_cursor


def insert_events(events: list[dict]) -> int:
    with db_cursor(commit=True) as cur:
        cur.executemany(
            """
            INSERT INTO events(source,event_type,ticker,quantity,price,amount,currency,event_ts,description,raw_json,recommendation_id)
            VALUES(:source,:event_type,:ticker,:quantity,:price,:amount,:currency,:event_ts,:description,:raw_json,:recommendation_id)
            """,
            events,
        )
    return len(events)


def rebuild_holdings() -> int:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM events ORDER BY event_ts ASC, id ASC")
        events = cur.fetchall()

    shares = defaultdict(float)
    avg_cost = defaultdict(float)

    for e in events:
        ticker = e["ticker"]
        if not ticker:
            continue
        qty = float(e["quantity"] or 0.0)
        price = float(e["price"] or 0.0)
        if e["event_type"] == "BUY" and qty > 0:
            prev_shares = shares[ticker]
            new_shares = prev_shares + qty
            if new_shares <= 0:
                continue
            avg_cost[ticker] = ((prev_shares * avg_cost[ticker]) + (qty * price)) / new_shares
            shares[ticker] = new_shares
        elif e["event_type"] == "SELL" and qty > 0:
            shares[ticker] = max(0.0, shares[ticker] - qty)

    now = datetime.utcnow().isoformat() + "Z"
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM holdings")
        for ticker, qty in shares.items():
            if qty <= 0:
                continue
            cur.execute(
                "INSERT INTO holdings(ticker,shares,avg_cost,last_updated) VALUES(?,?,?,?)",
                (ticker, qty, avg_cost[ticker], now),
            )
    return sum(1 for q in shares.values() if q > 0)


def fetch_holdings() -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT ticker, shares, avg_cost, last_updated FROM holdings ORDER BY ticker")
        rows = cur.fetchall()
    return [dict(row) for row in rows]
