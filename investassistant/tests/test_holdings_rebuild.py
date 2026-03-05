from backend.database import init_db, db_cursor
from backend.services.portfolio_service import rebuild_holdings


def test_rebuild_holdings_average_cost():
    init_db()
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM events")
        cur.execute("DELETE FROM holdings")
        cur.executemany(
            """
            INSERT INTO events(source,event_type,ticker,quantity,price,amount,currency,event_ts,description,raw_json,recommendation_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                ("t", "BUY", "AAPL", 10, 100, 1000, "USD", "2024-01-01T00:00:00Z", "", "{}", None),
                ("t", "BUY", "AAPL", 10, 200, 2000, "USD", "2024-01-02T00:00:00Z", "", "{}", None),
                ("t", "SELL", "AAPL", 5, 250, 1250, "USD", "2024-01-03T00:00:00Z", "", "{}", None),
            ],
        )

    rebuild_holdings()
    with db_cursor() as cur:
        cur.execute("SELECT shares, avg_cost FROM holdings WHERE ticker='AAPL'")
        row = cur.fetchone()
    assert round(row["shares"], 4) == 15
    assert round(row["avg_cost"], 4) == 150
