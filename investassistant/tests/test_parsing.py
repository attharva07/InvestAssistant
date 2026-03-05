from backend.services.robinhood_import import classify_event_type, parse_date, parse_money


def test_parse_money_handles_symbols_and_negatives():
    assert parse_money("$1,234.56") == 1234.56
    assert parse_money("-$12.34") == -12.34
    assert parse_money("(15.00)") == -15.0


def test_parse_date_iso():
    iso = parse_date("2024-01-05")
    assert "2024-01-05" in iso


def test_classify_event_type_keywords():
    assert classify_event_type("Market buy") == "BUY"
    assert classify_event_type("Dividend payment") == "DIVIDEND"
    assert classify_event_type("Unknown event") == "NOTE"
