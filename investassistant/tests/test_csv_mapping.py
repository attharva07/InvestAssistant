from backend.services.robinhood_import import detect_columns


def test_detect_columns_variants():
    headers = ["Trade Date", "Ticker", "Action", "Shares", "Fill Price", "Net Amount"]
    mapping = detect_columns(headers)
    assert mapping["date"] == "Trade Date"
    assert mapping["symbol"] == "Ticker"
    assert mapping["description"] == "Action"
    assert mapping["quantity"] == "Shares"
    assert mapping["price"] == "Fill Price"
    assert mapping["amount"] == "Net Amount"
