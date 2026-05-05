"""Finnhub data fetcher.

Fetches company news and market news from the Finnhub API.
Articles are stored in the existing articles table using the same
schema as news_fetcher.py.

API docs: https://finnhub.io/docs/api
"""

from __future__ import annotations

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
    date_str = published_iso[:10]
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
        tickers: List of ticker symbols.
        from_date: Start date in YYYY-MM-DD format.
        to_date: End date in YYYY-MM-DD format.

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
    """Fetch Finnhub news and store in the articles table."""
    tickers = load_tickers()
    company_records = fetch_company_news(api_key, tickers, from_date, to_date)
    market_records = fetch_market_news(api_key)

    all_records = company_records + market_records

    seen: set[str] = set()
    unique: list[dict] = []
    for rec in all_records:
        h = rec.get("content_hash")
        if h not in seen:
            seen.add(h)
            unique.append(rec)

    if not unique:
        return 0

    inserted = store.insert_articles(unique)
    logger.info(f"Finnhub: inserted {inserted} articles total")
    return inserted
