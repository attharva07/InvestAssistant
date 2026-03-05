import io

import asyncio
from fastapi import UploadFile

from backend.routes.importers import import_robinhood


def test_import_robinhood_returns_counts_and_skips_bad_rows(monkeypatch):
    monkeypatch.setattr("backend.routes.importers.insert_events", lambda records: records)
    monkeypatch.setattr("backend.routes.importers.rebuild_holdings", lambda: 0)

    csv_text = """Activity Date,Symbol,Description,Quantity,Price,Amount
2026-03-05,AAPL,Market buy,1,100,100
,TSLA,Market buy,2,200,400
"""
    upload = UploadFile(filename="robinhood.csv", file=io.BytesIO(csv_text.encode("utf-8")))

    payload = asyncio.run(import_robinhood(request=None, file=upload))

    assert payload["imported_count"] == 1
    assert payload["records_received"] == 1
    assert payload["skipped_count"] == 1
    assert payload["errors_sample"][0]["date"] == ""
