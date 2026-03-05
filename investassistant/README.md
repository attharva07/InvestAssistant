# InvestAssistant (Local-only MVP)

InvestAssistant is an advisory-only local prototype:
- **FastAPI** backend
- **Streamlit** frontend
- **SQLite** event-sourced storage (immutable event log + derived holdings)
- **No Robinhood API** usage
- **No trade execution**

## Features
- Import Robinhood 1-year activity CSV from upload or `./data/filename.csv`
- Heuristic column detection across common column variants
- Immutable event log storage with raw row JSON for audit
- Holdings rebuilt from events using average-cost accounting
- Local market price cache with yfinance and delayed-data fallback behavior
- Daily brief: 1D/1W change, RSI(14), 6mo drawdown, risk flags
- Recommendations + reminders workflow with in-app reminder resolution
- Local scheduler (APScheduler) to regularly evaluate due reminders

## Run
```bash
cd investassistant
pip install -r requirements.txt
uvicorn backend.main:app --reload
streamlit run frontend/app.py
```

## Notes / assumptions
- Database is local file: `investassistant/investassistant.db`.
- SQLite runs with WAL mode enabled.
- If live price fetch fails, app uses cached data where possible and marks data as delayed.
- Watchlist is optional and currently read from `preferences` key `watchlist` as comma-separated tickers.

## API endpoints
- `POST /import/robinhood`
  - multipart file upload (`file`) **or** JSON body `{ "filename": "robinhood_1y.csv" }`
- `GET /portfolio`
- `POST /events`
- `GET /report/daily`
- `POST /recommendations/generate`
- `GET /reminders`
- `POST /reminders/{id}/resolve` with `{ "status": "done"|"ignored" }`

## Tests
```bash
cd investassistant
pytest -q
```
