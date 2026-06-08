## Fixes Applied

- **domains/finance/service.py** — Fixed double-fetch in `analyze_stock()`: removed inner try/except that silently swallowed errors and the redundant second `stock.info` / `stock.history()` calls; now fetches each exactly once.
- **domains/finance/service.py** — Replaced fake sentiment scoring (`50 + len(news) * 2`) with NLTK VADER: scores each news headline's compound value, averages them, maps to 0–100; defaults to 50.0 if no headlines.
- **domains/finance/service.py** — Renamed `get_net_worth()` to `_compute_net_worth()` (pure read, no DB write); added `log_net_worth_snapshot()` which calls `_compute_net_worth()` then persists a `NetWorthLog` row.
- **domains/finance/service.py** — Updated `get_financial_summary()` to call `_compute_net_worth()` instead of the old `get_net_worth()`.
- **domains/finance/service.py** — Fixed N+1 query in `get_budgets_with_spending()`: replaced per-category `CardTransaction` loop queries with a single `func.sum` + `group_by` aggregated query.
- **domains/finance/service.py** — Added delete service functions: `delete_holding`, `delete_account`, `delete_credit_card`, `delete_budget`, `delete_savings_goal`, `delete_alert`.
- **domains/finance/router.py** — `GET /finance/net-worth` now calls `_compute_net_worth()` (no longer writes a log row on every GET).
- **domains/finance/router.py** — Added `POST /finance/net-worth/snapshot` that calls `log_net_worth_snapshot()` to explicitly persist a net worth log row.
- **domains/finance/router.py** — Added DELETE endpoints: `/finance/holdings/{ticker}`, `/finance/accounts/{account_id}`, `/finance/cards/{card_id}`, `/finance/budgets/{category}`, `/finance/goals/{goal_id}`, `/finance/alerts/{alert_id}`; each returns `{"deleted": true}` or 404.
- **requirements.txt** — Added `nltk` dependency for VADER sentiment analysis.
- **GlobeWatch cleanup** — Searched all files for `globe`, `GDELT`, `MapLibre`, `deck.gl`, `region marker`; no stale files found, nothing to delete.

## Manual Steps Required

1. **Install new dependency:**
   ```
   pip install nltk
   ```

2. **Download VADER lexicon** (happens automatically on first `analyze_stock()` call via `nltk.download('vader_lexicon', quiet=True)`, but you can pre-download it now):
   ```
   python -c "import nltk; nltk.download('vader_lexicon')"
   ```

3. **No database migrations needed** — no schema changes were made.
