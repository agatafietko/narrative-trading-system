# Data Pipeline Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the data pipeline to reliably fetch from yfinance, FRED, and Finnhub for 2026-01-01 → 2026-04-05, with a validation layer that fails loudly when any source returns 0 records.

**Architecture:** Three fetchers run sequentially in `fetch_historical_data.py`. A new `finnhub_fetcher.py` fetches company news and market news from the Finnhub API and stores into the existing `articles` table. A `validate_fetch_results()` function exits with code 1 if any fetcher returned 0 records, causing the GitHub Actions job to fail visibly.

**Tech Stack:** Python 3.12, requests, finnhub-python, pytest, GitHub Actions

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/data/fetchers/finnhub_fetcher.py` | Fetch company + market news from Finnhub API |
| Create | `tests/data/fetchers/test_finnhub_fetcher.py` | Unit tests for Finnhub fetcher |
| Create | `tests/data/fetchers/test_fetch_historical_data.py` | Tests for validation layer |
| Modify | `scripts/fetch_historical_data.py` | Add Finnhub, add validation, update date defaults |
| Modify | `src/data/fetchers/yfinance_fetcher.py` | Update default start/end dates |
| Modify | `src/data/fetchers/fred_fetcher.py` | Update default start/end dates |
| Modify | `.github/workflows/weekly_run.yml` | Add FINNHUB_API_KEY env var |
| Modify | `requirements.txt` | Add finnhub-python |

---

## Task 1: Add finnhub-python to dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add finnhub-python to requirements.txt**

Open `requirements.txt` and add this line (keep alphabetical order with other packages):

```
finnhub-python>=2.4.20
```

- [ ] **Step 2: Install it locally to verify it resolves**

```bash
pip install finnhub-python
```

Expected output: `Successfully installed finnhub-python-...` (or "already satisfied")

- [ ] **Step 3: Commit**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
git add requirements.txt
git commit -m "deps: add finnhub-python"
```

---

## Task 2: Create tests directory and write failing Finnhub fetcher tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/data/__init__.py`
- Create: `tests/data/fetchers/__init__.py`
- Create: `tests/data/fetchers/test_finnhub_fetcher.py`

- [ ] **Step 1: Create the test package structure**

```bash
mkdir -p /Users/agatka_jednorozek/narrative-trading-system/tests/data/fetchers
touch /Users/agatka_jednorozek/narrative-trading-system/tests/__init__.py
touch /Users/agatka_jednorozek/narrative-trading-system/tests/data/__init__.py
touch /Users/agatka_jednorozek/narrative-trading-system/tests/data/fetchers/__init__.py
```

- [ ] **Step 2: Write the test file**

Create `tests/data/fetchers/test_finnhub_fetcher.py`:

```python
"""Tests for Finnhub fetcher."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.data.fetchers.finnhub_fetcher import (
    fetch_company_news,
    fetch_market_news,
    fetch_and_store,
)


SAMPLE_ARTICLE = {
    "category": "company news",
    "datetime": 1735689600,  # 2026-01-01 00:00:00 UTC
    "headline": "SPY hits record high",
    "id": 123456,
    "image": "",
    "related": "SPY",
    "source": "Reuters",
    "summary": "SPY ETF reached a new all-time high on Wednesday.",
    "url": "https://reuters.com/spy-record",
}

SAMPLE_MARKET_ARTICLE = {
    "category": "general",
    "datetime": 1735689600,
    "headline": "Fed holds rates steady",
    "id": 789012,
    "image": "",
    "related": "",
    "source": "Bloomberg",
    "summary": "The Federal Reserve held interest rates steady at its January meeting.",
    "url": "https://bloomberg.com/fed-rates",
}


class TestFetchCompanyNews:
    def test_returns_list_of_records(self):
        """fetch_company_news returns a list of article dicts."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.company_news.return_value = [SAMPLE_ARTICLE]

            results = fetch_company_news(
                api_key="test_key",
                tickers=["SPY"],
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert len(results) == 1
        assert results[0]["source"] == "Reuters"
        assert results[0]["title"] == "SPY hits record high"

    def test_record_has_required_fields(self):
        """Each record has all fields required by insert_articles."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.company_news.return_value = [SAMPLE_ARTICLE]

            results = fetch_company_news(
                api_key="test_key",
                tickers=["SPY"],
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        record = results[0]
        for field in ("source", "title", "content", "url", "published_at", "known_at", "content_hash"):
            assert field in record, f"Missing field: {field}"

    def test_deduplicates_by_content_hash(self):
        """Duplicate articles (same source+title+date) are deduplicated."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            # Return same article twice (e.g., from two tickers)
            mock_client.company_news.return_value = [SAMPLE_ARTICLE, SAMPLE_ARTICLE]

            results = fetch_company_news(
                api_key="test_key",
                tickers=["SPY"],
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert len(results) == 1

    def test_skips_ticker_on_api_error(self):
        """A failing ticker is skipped; other tickers still processed."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.company_news.side_effect = [
                Exception("API error"),
                [SAMPLE_ARTICLE],
            ]

            results = fetch_company_news(
                api_key="test_key",
                tickers=["BAD", "SPY"],
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert len(results) == 1
        assert results[0]["title"] == "SPY hits record high"


class TestFetchMarketNews:
    def test_returns_list_of_records(self):
        """fetch_market_news returns a list of article dicts."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.general_news.return_value = [SAMPLE_MARKET_ARTICLE]

            results = fetch_market_news(api_key="test_key")

        assert len(results) >= 1
        assert results[0]["source"] == "Bloomberg"

    def test_record_has_required_fields(self):
        """Each market news record has all fields required by insert_articles."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.general_news.return_value = [SAMPLE_MARKET_ARTICLE]

            results = fetch_market_news(api_key="test_key")

        record = results[0]
        for field in ("source", "title", "content", "url", "published_at", "known_at", "content_hash"):
            assert field in record, f"Missing field: {field}"


class TestFetchAndStore:
    def test_returns_inserted_count(self):
        """fetch_and_store returns the number of records inserted."""
        mock_store = MagicMock()
        mock_store.insert_articles.return_value = 5

        with patch("src.data.fetchers.finnhub_fetcher.fetch_company_news", return_value=[{}] * 3), \
             patch("src.data.fetchers.finnhub_fetcher.fetch_market_news", return_value=[{}] * 2):
            count = fetch_and_store(
                store=mock_store,
                api_key="test_key",
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert count == 5
        mock_store.insert_articles.assert_called_once()

    def test_returns_zero_when_no_articles(self):
        """fetch_and_store returns 0 when no articles are fetched."""
        mock_store = MagicMock()

        with patch("src.data.fetchers.finnhub_fetcher.fetch_company_news", return_value=[]), \
             patch("src.data.fetchers.finnhub_fetcher.fetch_market_news", return_value=[]):
            count = fetch_and_store(
                store=mock_store,
                api_key="test_key",
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert count == 0
        mock_store.insert_articles.assert_not_called()
```

- [ ] **Step 3: Run tests to verify they fail (module doesn't exist yet)**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
python -m pytest tests/data/fetchers/test_finnhub_fetcher.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'src.data.fetchers.finnhub_fetcher'`

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/
git commit -m "test: add failing tests for finnhub_fetcher"
```

---

## Task 3: Implement finnhub_fetcher.py

**Files:**
- Create: `src/data/fetchers/finnhub_fetcher.py`

- [ ] **Step 1: Create the fetcher**

Create `src/data/fetchers/finnhub_fetcher.py`:

```python
"""Finnhub data fetcher.

Fetches company news and market news from the Finnhub API.
Articles are stored in the existing articles table using the same
schema as news_fetcher.py.

API docs: https://finnhub.io/docs/api
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import finnhub
import yaml

from src.state.store import DataStore
from src.utils.logging import get_logger
from src.utils.reproducibility import hash_data_record
from src.utils.temporal import article_known_at

logger = get_logger("fetcher.finnhub")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "settings.yaml"

# Finnhub market news categories to fetch
MARKET_NEWS_CATEGORIES = ["general", "forex"]


def load_tickers() -> list[str]:
    """Load tickers from the investment universe config."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return [info["ticker"] for info in config["universe"].values()]


def _unix_to_iso(unix_ts: int) -> str:
    """Convert Unix timestamp to ISO 8601 string (UTC)."""
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()


def _build_record(article: dict) -> dict:
    """Convert a Finnhub article dict to the articles table schema."""
    published_iso = _unix_to_iso(article["datetime"])
    date_str = published_iso[:10]  # YYYY-MM-DD
    source = article.get("source", "finnhub")
    title = article.get("headline", "")
    content = article.get("summary", "")[:2000]

    return {
        "source": source,
        "title": title,
        "content": content,
        "url": article.get("url", ""),
        "published_at": published_iso,
        "known_at": article_known_at(published_iso),
        "content_hash": hash_data_record(source, title, date_str),
    }


def fetch_company_news(
    api_key: str,
    tickers: list[str],
    from_date: str,
    to_date: str,
) -> list[dict]:
    """Fetch news articles for each ticker in the universe.

    Args:
        api_key: Finnhub API key.
        tickers: List of ticker symbols (e.g. ["SPY", "QQQ"]).
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).

    Returns:
        Deduplicated list of article records.
    """
    client = finnhub.Client(api_key=api_key)
    seen_hashes: set[str] = set()
    records: list[dict] = []

    for ticker in tickers:
        logger.info(f"Fetching Finnhub company news for {ticker}...")
        try:
            articles = client.company_news(ticker, _from=from_date, to=to_date)
            for article in articles:
                rec = _build_record(article)
                if rec["content_hash"] not in seen_hashes:
                    seen_hashes.add(rec["content_hash"])
                    records.append(rec)
        except Exception as e:
            logger.warning(f"Finnhub company news error for {ticker}: {e}")
            continue

    logger.info(f"Finnhub company news: {len(records)} unique articles")
    return records


def fetch_market_news(api_key: str) -> list[dict]:
    """Fetch general market and forex news from Finnhub.

    Args:
        api_key: Finnhub API key.

    Returns:
        Deduplicated list of article records.
    """
    client = finnhub.Client(api_key=api_key)
    seen_hashes: set[str] = set()
    records: list[dict] = []

    for category in MARKET_NEWS_CATEGORIES:
        logger.info(f"Fetching Finnhub market news (category: {category})...")
        try:
            articles = client.general_news(category, min_id=0)
            for article in articles:
                rec = _build_record(article)
                if rec["content_hash"] not in seen_hashes:
                    seen_hashes.add(rec["content_hash"])
                    records.append(rec)
        except Exception as e:
            logger.warning(f"Finnhub market news error for category '{category}': {e}")
            continue

    logger.info(f"Finnhub market news: {len(records)} unique articles")
    return records


def fetch_and_store(
    store: DataStore,
    api_key: str,
    from_date: str = "2026-01-01",
    to_date: str = "2026-04-05",
) -> int:
    """Fetch Finnhub news and store in the articles table.

    Args:
        store: DataStore instance.
        api_key: Finnhub API key.
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).

    Returns:
        Number of records inserted.
    """
    tickers = load_tickers()
    company_records = fetch_company_news(api_key, tickers, from_date, to_date)
    market_records = fetch_market_news(api_key)

    all_records = company_records + market_records

    # Final deduplication across both sources
    seen: set[str] = set()
    unique: list[dict] = []
    for rec in all_records:
        if rec["content_hash"] not in seen:
            seen.add(rec["content_hash"])
            unique.append(rec)

    if not unique:
        return 0

    inserted = store.insert_articles(unique)
    logger.info(f"Finnhub: inserted {inserted} articles total")
    return inserted
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
python -m pytest tests/data/fetchers/test_finnhub_fetcher.py -v
```

Expected output: All tests PASS, 0 failures.

- [ ] **Step 3: Commit**

```bash
git add src/data/fetchers/finnhub_fetcher.py
git commit -m "feat: add finnhub_fetcher for company and market news"
```

---

## Task 4: Write failing test for validation layer

**Files:**
- Create: `tests/data/fetchers/test_fetch_historical_data.py`

- [ ] **Step 1: Write the test**

Create `tests/data/fetchers/test_fetch_historical_data.py`:

```python
"""Tests for fetch_historical_data validation layer."""
from __future__ import annotations

import sys
import pytest


def test_validate_fetch_results_passes_when_all_nonzero():
    """validate_fetch_results does not exit when all counts > 0."""
    # Import here so we get a fresh module each test
    from scripts.fetch_historical_data import validate_fetch_results

    # Should not raise SystemExit
    validate_fetch_results({"yfinance": 715, "fred": 120, "finnhub": 300})


def test_validate_fetch_results_exits_when_yfinance_zero():
    """validate_fetch_results exits 1 when yfinance returns 0 records."""
    from scripts.fetch_historical_data import validate_fetch_results

    with pytest.raises(SystemExit) as exc_info:
        validate_fetch_results({"yfinance": 0, "fred": 120, "finnhub": 300})

    assert exc_info.value.code == 1


def test_validate_fetch_results_exits_when_fred_zero():
    """validate_fetch_results exits 1 when fred returns 0 records."""
    from scripts.fetch_historical_data import validate_fetch_results

    with pytest.raises(SystemExit) as exc_info:
        validate_fetch_results({"yfinance": 715, "fred": 0, "finnhub": 300})

    assert exc_info.value.code == 1


def test_validate_fetch_results_exits_when_finnhub_zero():
    """validate_fetch_results exits 1 when finnhub returns 0 records."""
    from scripts.fetch_historical_data import validate_fetch_results

    with pytest.raises(SystemExit) as exc_info:
        validate_fetch_results({"yfinance": 715, "fred": 120, "finnhub": 0})

    assert exc_info.value.code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
python -m pytest tests/data/fetchers/test_fetch_historical_data.py -v 2>&1 | head -20
```

Expected: `ImportError` or `AttributeError` — `validate_fetch_results` doesn't exist yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/data/fetchers/test_fetch_historical_data.py
git commit -m "test: add failing tests for validation layer"
```

---

## Task 5: Update fetch_historical_data.py

**Files:**
- Modify: `scripts/fetch_historical_data.py`

- [ ] **Step 1: Replace the entire file with the updated version**

```python
#!/usr/bin/env python3
"""Fetch historical data for backtesting.

Usage:
    python scripts/fetch_historical_data.py [--start 2026-01-01] [--end 2026-04-05]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.data.fetchers import yfinance_fetcher, fred_fetcher, finnhub_fetcher
from src.state.store import DataStore
from src.utils.logging import setup_logging

load_dotenv()


def validate_fetch_results(counts: dict[str, int]) -> None:
    """Exit with code 1 if any data source returned 0 records.

    Args:
        counts: Mapping of source name to number of records inserted.

    Raises:
        SystemExit: If any source returned 0 records.
    """
    failed = [source for source, count in counts.items() if count == 0]
    if failed:
        for source in failed:
            print(f"ERROR: {source} returned 0 records — check credentials and API availability", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Fetch historical data")
    parser.add_argument("--start", default="2026-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-04-05", help="End date (YYYY-MM-DD)")
    parser.add_argument("--skip-market", action="store_true", help="Skip market data")
    parser.add_argument("--skip-fred", action="store_true", help="Skip FRED data")
    parser.add_argument("--skip-finnhub", action="store_true", help="Skip Finnhub data")
    args = parser.parse_args()

    logger = setup_logging("INFO")
    store = DataStore()

    logger.info(f"Fetching data from {args.start} to {args.end}")

    counts: dict[str, int] = {}

    # Fetch market data (yfinance)
    if not args.skip_market:
        logger.info("=" * 60)
        logger.info("Fetching market data (yfinance)...")
        logger.info("=" * 60)
        count = yfinance_fetcher.fetch_and_store(store, args.start, args.end)
        logger.info(f"Market data: {count} records stored")
        counts["yfinance"] = count

    # Fetch FRED data
    if not args.skip_fred:
        fred_key = os.getenv("FRED_API_KEY")
        if not fred_key:
            logger.error("FRED_API_KEY not set — cannot fetch FRED data")
            counts["fred"] = 0
        else:
            logger.info("=" * 60)
            logger.info("Fetching FRED economic data...")
            logger.info("=" * 60)
            count = fred_fetcher.fetch_and_store(store, fred_key, args.start, args.end)
            logger.info(f"FRED data: {count} records stored")
            counts["fred"] = count

    # Fetch Finnhub news
    if not args.skip_finnhub:
        finnhub_key = os.getenv("FINNHUB_API_KEY")
        if not finnhub_key:
            logger.error("FINNHUB_API_KEY not set — cannot fetch Finnhub data")
            counts["finnhub"] = 0
        else:
            logger.info("=" * 60)
            logger.info("Fetching Finnhub news and sentiment...")
            logger.info("=" * 60)
            count = finnhub_fetcher.fetch_and_store(store, finnhub_key, args.start, args.end)
            logger.info(f"Finnhub data: {count} records stored")
            counts["finnhub"] = count

    logger.info("=" * 60)
    logger.info(f"Data fetch complete. Results: {counts}")

    validate_fetch_results(counts)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run validation tests to verify they pass**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
python -m pytest tests/data/fetchers/test_fetch_historical_data.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_historical_data.py
git commit -m "feat: add finnhub fetcher and validation layer to fetch_historical_data"
```

---

## Task 6: Update yfinance and FRED default dates

**Files:**
- Modify: `src/data/fetchers/yfinance_fetcher.py`
- Modify: `src/data/fetchers/fred_fetcher.py`

- [ ] **Step 1: Update yfinance_fetcher.py default start_date**

In `src/data/fetchers/yfinance_fetcher.py`, find the `fetch_market_data` function signature (line ~30) and change the default:

Old:
```python
def fetch_market_data(
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> pd.DataFrame:
```

New:
```python
def fetch_market_data(
    start_date: str = "2026-01-01",
    end_date: str = "2026-04-05",
) -> pd.DataFrame:
```

Also update `fetch_and_store` signature in the same file:

Old:
```python
def fetch_and_store(
    store: DataStore,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> int:
```

New:
```python
def fetch_and_store(
    store: DataStore,
    start_date: str = "2026-01-01",
    end_date: str = "2026-04-05",
) -> int:
```

- [ ] **Step 2: Update fred_fetcher.py default start_date**

In `src/data/fetchers/fred_fetcher.py`, find `fetch_fred_data` (line ~31) and change:

Old:
```python
def fetch_fred_data(
    api_key: str,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> list[dict]:
```

New:
```python
def fetch_fred_data(
    api_key: str,
    start_date: str = "2026-01-01",
    end_date: str = "2026-04-05",
) -> list[dict]:
```

Also update `fetch_and_store`:

Old:
```python
def fetch_and_store(
    store: DataStore,
    api_key: str,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> int:
```

New:
```python
def fetch_and_store(
    store: DataStore,
    api_key: str,
    start_date: str = "2026-01-01",
    end_date: str = "2026-04-05",
) -> int:
```

- [ ] **Step 3: Run all tests to confirm nothing broke**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/data/fetchers/yfinance_fetcher.py src/data/fetchers/fred_fetcher.py
git commit -m "feat: update yfinance and fred default date range to 2026-01-01–2026-04-05"
```

---

## Task 7: Update GitHub Actions workflow

**Files:**
- Modify: `.github/workflows/weekly_run.yml`

- [ ] **Step 1: Add FINNHUB_API_KEY to the fetch-data job env block**

In `.github/workflows/weekly_run.yml`, find the `fetch-data` job's `env` block:

Old:
```yaml
      - name: Fetch market data
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
        run: python scripts/fetch_historical_data.py
```

New:
```yaml
      - name: Fetch market data
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
          FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}
        run: python scripts/fetch_historical_data.py --start 2026-01-01 --end 2026-04-05
```

- [ ] **Step 2: Verify the YAML is valid**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
python -c "import yaml; yaml.safe_load(open('.github/workflows/weekly_run.yml')); print('YAML valid')"
```

Expected: `YAML valid`

- [ ] **Step 3: Commit and push**

```bash
git add .github/workflows/weekly_run.yml
git commit -m "ci: add FINNHUB_API_KEY and fix date range in fetch-data job"
git push origin main
```

---

## Task 8: Run all tests and verify

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
python -m pytest tests/ -v
```

Expected: All tests PASS, 0 failures.

- [ ] **Step 2: Verify imports work end to end**

```bash
cd /Users/agatka_jednorozek/narrative-trading-system
python -c "
from src.data.fetchers import yfinance_fetcher, fred_fetcher, finnhub_fetcher
from scripts.fetch_historical_data import validate_fetch_results
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 3: Push all commits to GitHub**

```bash
git push origin main
```
