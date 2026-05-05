# Data Pipeline Improvement — Design Spec

**Date:** 2026-05-05  
**Scope:** Narrative Trading System — data input layer  
**Status:** Approved

---

## Problem

On the last full run, only ~20% of expected data was retrieved. Root causes:

1. `fetch_historical_data.py` only calls yfinance and FRED — news, Reddit, and GDELT fetchers are never invoked by the CI workflow
2. `FRED_API_KEY` was missing from GitHub Actions secrets, silently skipping FRED
3. Silent failure pattern: all fetchers log warnings and return 0 on error — no loud failure, no CI job failure, downstream jobs run on empty data

---

## Goals

- Fix the data pipeline to reliably retrieve data from 3 sources: yfinance, FRED, Finnhub
- Scope all fetching to **2026-01-01 → 2026-04-05**
- Add a validation layer that fails loudly when any source returns 0 records

---

## Architecture

Three fetchers run sequentially in `fetch_historical_data.py`:

```
fetch_historical_data.py
  ├── yfinance_fetcher.fetch_and_store()   → market_data table
  ├── fred_fetcher.fetch_and_store()       → fred_series table
  ├── finnhub_fetcher.fetch_and_store()    → articles table
  └── validate_fetch_results()             → exits 1 if any source returned 0 records
```

The GitHub Actions workflow passes all 3 API keys (`FRED_API_KEY`, `FINNHUB_API_KEY`) and uses the fixed date range. If validation fails, the job exits non-zero and downstream jobs (baselines, full system) do not run.

---

## Components

### 1. yfinance fetcher (existing — date range update only)

- File: `src/data/fetchers/yfinance_fetcher.py`
- Change: update default `start_date` from `2020-01-01` to `2026-01-01`, `end_date` to `2026-04-05`
- No other changes needed

### 2. FRED fetcher (existing — date range update only)

- File: `src/data/fetchers/fred_fetcher.py`
- Change: update default `start_date` from `2020-01-01` to `2026-01-01`, `end_date` to `2026-04-05`
- No other changes needed

### 3. Finnhub fetcher (new)

- File: `src/data/fetchers/finnhub_fetcher.py`
- Data fetched:
  - **Company news**: for each of the 11 tickers in the universe, fetch news articles in the date range via Finnhub `/company-news` endpoint
  - **Market news**: general market/economy news via Finnhub `/news` endpoint (categories: `general`, `forex`)
- Storage: existing `articles` table — same schema as `news_fetcher.py`
  - Fields: source, title, content, url, published_at, known_at, content_hash
  - `known_at` = article `datetime` field from Finnhub (actual publish time)
  - Deduplication: SHA-256 hash of `source + title + date`, skips duplicates on insert
- Auth: `FINNHUB_API_KEY` environment variable

### 4. Validation layer (new)

- Function: `validate_fetch_results(counts: dict[str, int])` in `fetch_historical_data.py`
- Logic: if any source count is 0, log which source failed and `sys.exit(1)`
- No retries, no fallbacks — hard stop for visibility

### 5. fetch_historical_data.py (updated)

- Default `--start`: `2026-01-01`
- Default `--end`: `2026-04-05`
- Add Finnhub fetcher invocation after FRED
- Add validation call after all 3 fetchers complete
- Pass `FINNHUB_API_KEY` from environment

### 6. GitHub Actions workflow (updated)

- File: `.github/workflows/weekly_run.yml`
- Add `FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}` to `fetch-data` job env
- Update any hardcoded date defaults to match 2026 range

---

## Data Flow

```
GitHub Actions (fetch-data job)
  │
  ├─ yfinance → 11 tickers × ~65 trading days = ~715 OHLCV rows → market_data
  ├─ FRED → 8 series × ~65 days (daily) or fewer (monthly/quarterly) → fred_series
  ├─ Finnhub → company news (11 tickers) + market news → articles
  └─ validate → all counts > 0? → pass : exit 1
```

---

## Out of Scope

- Reddit fetcher (not used in this run)
- GDELT fetcher (not used in this run)
- News fetcher / NewsAPI (replaced by Finnhub for this scope)
- Retry logic or fallback sources
- Historical data before 2026-01-01
