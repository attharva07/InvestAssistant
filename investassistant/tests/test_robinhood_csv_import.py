from backend.services.robinhood_import import parse_csv_text


def test_parse_csv_text_skips_blank_date_rows():
    csv_text = """Activity Date,Symbol,Description,Quantity,Price,Amount
2026-03-05,AAPL,Market buy,1,100,100
,TSLA,Market buy,2,200,400
03/07/2026,MSFT,Market buy,3,300,900
"""

    events, mapping, stats = parse_csv_text(csv_text)

    assert len(events) == 2
    assert stats["imported_count"] == 2
    assert stats["skipped_count"] == 1
    assert len(stats["errors_sample"]) == 1
    assert stats["errors_sample"][0]["row"] == 3
    assert stats["errors_sample"][0]["date"] == ""
    assert mapping["date"] == "Activity Date"
