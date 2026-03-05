from datetime import timezone

import pytest

from backend.services.robinhood_import import classify_event_type, parse_date, parse_money


def test_parse_money_handles_symbols_and_negatives():
    assert parse_money("$1,234.56") == 1234.56
    assert parse_money("-$12.34") == -12.34
    assert parse_money("(15.00)") == -15.0


def test_parse_date_iso_z():
    parsed = parse_date("2026-03-05T12:34:56Z")
    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-03-05T12:34:56+00:00"


def test_parse_date_date_only():
    parsed = parse_date("2026-03-05")
    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-03-05T00:00:00+00:00"


def test_parse_date_us_date():
    parsed = parse_date("03/05/2026")
    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-03-05T00:00:00+00:00"


def test_parse_date_empty_raises():
    with pytest.raises(ValueError, match="empty date"):
        parse_date("")


def test_parse_date_blank_raises():
    with pytest.raises(ValueError, match="empty date"):
        parse_date("   ")


def test_classify_event_type_keywords():
    assert classify_event_type("Market buy") == "BUY"
    assert classify_event_type("Dividend payment") == "DIVIDEND"
    assert classify_event_type("Unknown event") == "NOTE"
