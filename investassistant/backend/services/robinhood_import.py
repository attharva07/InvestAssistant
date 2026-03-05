import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

DATE_CANDIDATES = ["Activity Date", "Date", "Trade Date", "Process Date", "Settle Date"]
SYMBOL_CANDIDATES = ["Symbol", "Ticker", "Instrument", "Underlying Symbol"]
DESC_CANDIDATES = ["Description", "Activity", "Type", "Trans Code", "Action"]
QTY_CANDIDATES = ["Quantity", "Shares", "Units"]
PRICE_CANDIDATES = ["Price", "Fill Price", "Average Price"]
AMOUNT_CANDIDATES = ["Amount", "Total", "Net Amount", "Dollar Amount", "Value"]


@dataclass
class ParsedEvent:
    source: str
    event_type: str
    ticker: str | None
    quantity: float | None
    price: float | None
    amount: float | None
    currency: str
    event_ts: str
    description: str | None
    raw_json: str


class MappingError(ValueError):
    pass


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _first_match(headers: list[str], candidates: list[str]) -> str | None:
    canon = {_normalize(h): h for h in headers}
    for c in candidates:
        if _normalize(c) in canon:
            return canon[_normalize(c)]
    return None


def detect_columns(headers: list[str]) -> dict[str, str | None]:
    mapping = {
        "date": _first_match(headers, DATE_CANDIDATES),
        "symbol": _first_match(headers, SYMBOL_CANDIDATES),
        "description": _first_match(headers, DESC_CANDIDATES),
        "quantity": _first_match(headers, QTY_CANDIDATES),
        "price": _first_match(headers, PRICE_CANDIDATES),
        "amount": _first_match(headers, AMOUNT_CANDIDATES),
    }
    if not mapping["date"]:
        raise MappingError(f"Unable to detect date column. headers={headers}")
    if not mapping["description"]:
        raise MappingError(f"Unable to detect description column. headers={headers}")
    return mapping


def parse_money(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    cleaned = raw.replace("$", "").replace(",", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    cleaned = cleaned.replace("+", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("empty date")

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError(f"Unable to parse date: {value}")


def classify_event_type(description: str) -> str:
    d = description.lower()
    if "buy" in d:
        return "BUY"
    if "sell" in d:
        return "SELL"
    if "dividend" in d:
        return "DIVIDEND"
    if "deposit" in d or "transfer in" in d:
        return "DEPOSIT"
    if "withdraw" in d or "transfer out" in d:
        return "WITHDRAW"
    if "fee" in d or "interest" in d:
        return "FEE"
    return "NOTE"


def parse_csv_text(
    csv_text: str, source: str = "robinhood_csv"
) -> tuple[list[ParsedEvent], dict[str, str | None], dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = reader.fieldnames or []
    mapping = detect_columns(headers)
    events: list[ParsedEvent] = []
    skipped_count = 0
    errors_sample: list[dict[str, Any]] = []

    for row_index, row in enumerate(reader, start=2):
        if all(not str(value or "").strip() for value in row.values()):
            continue

        desc = str(row.get(mapping["description"] or "", "")).strip()
        raw_date = str(row.get(mapping["date"] or "", "")).strip()
        try:
            parsed_date = parse_date(raw_date)
        except ValueError as e:
            skipped_count += 1
            if len(errors_sample) < 5:
                errors_sample.append({"row": row_index, "date": raw_date, "error": str(e)})
            continue

        event_type = classify_event_type(desc)
        event = ParsedEvent(
            source=source,
            event_type=event_type,
            ticker=(row.get(mapping["symbol"] or "") or None),
            quantity=parse_money(row.get(mapping["quantity"] or "")),
            price=parse_money(row.get(mapping["price"] or "")),
            amount=parse_money(row.get(mapping["amount"] or "")),
            currency="USD",
            event_ts=parsed_date.isoformat(),
            description=desc,
            raw_json=json.dumps(row),
        )
        if event.ticker:
            event.ticker = str(event.ticker).strip().upper()
        events.append(event)

    stats = {
        "imported_count": len(events),
        "skipped_count": skipped_count,
        "errors_sample": errors_sample,
    }
    return events, mapping, stats


def load_and_parse_csv(path: str) -> tuple[list[ParsedEvent], dict[str, str | None], dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return parse_csv_text(f.read())
