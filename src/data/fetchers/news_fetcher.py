"""News article fetcher.

Fetches articles from NewsAPI and RSS feeds. Each article gets a known_at
timestamp equal to its publication time.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import requests
import yaml

from src.state.store import DataStore
from src.utils.logging import get_logger
from src.utils.reproducibility import hash_data_record
from src.utils.temporal import article_known_at

logger = get_logger("fetcher.news")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "data_sources.yaml"


def load_news_config() -> dict:
    """Load news source configuration."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config


def fetch_newsapi(
    api_key: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Fetch articles from NewsAPI.

    Args:
        api_key: NewsAPI key.
        from_date: Start date (YYYY-MM-DD). Defaults to 7 days ago.
        to_date: End date (YYYY-MM-DD). Defaults to today.

    Returns:
        List of article records ready for storage.
    """
    config = load_news_config()
    newsapi_config = config["newsapi"]

    if from_date is None:
        from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if to_date is None:
        to_date = datetime.now().strftime("%Y-%m-%d")

    records = []
    domains = ",".join(newsapi_config["domains"])

    for keyword in newsapi_config["keywords"]:
        try:
            resp = requests.get(
                f"{newsapi_config['base_url']}/everything",
                params={
                    "q": keyword,
                    "domains": domains,
                    "from": from_date,
                    "to": to_date,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 20,
                    "apiKey": api_key,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for article in data.get("articles", []):
                published = article.get("publishedAt", "")
                if not published:
                    continue

                record = {
                    "source": article.get("source", {}).get("name", "unknown"),
                    "title": article.get("title", ""),
                    "content": article.get("content") or article.get("description", ""),
                    "url": article.get("url", ""),
                    "published_at": published,
                    "known_at": article_known_at(published),
                    "content_hash": hash_data_record(
                        article.get("source", {}).get("name", ""),
                        article.get("title", ""),
                        published[:10],
                    ),
                }
                records.append(record)

        except Exception as e:
            logger.warning(f"NewsAPI error for keyword '{keyword}': {e}")
            continue

    # Deduplicate by content_hash
    seen = set()
    unique = []
    for r in records:
        if r["content_hash"] not in seen:
            seen.add(r["content_hash"])
            unique.append(r)

    logger.info(f"NewsAPI: fetched {len(unique)} unique articles")
    return unique


def fetch_rss_feeds() -> list[dict]:
    """Fetch articles from configured RSS feeds.

    Returns:
        List of article records.
    """
    config = load_news_config()
    feeds = config.get("rss_feeds", [])

    records = []
    for feed_config in feeds:
        name = feed_config["name"]
        url = feed_config["url"]

        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:  # Limit per feed
                published = entry.get("published", entry.get("updated", ""))
                title = entry.get("title", "")
                content = entry.get("summary", "")

                if not title:
                    continue

                # Parse published date
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_dt = datetime(*entry.published_parsed[:6])
                    published_str = pub_dt.isoformat()
                else:
                    published_str = published or datetime.now().isoformat()

                record = {
                    "source": name,
                    "title": title,
                    "content": content[:2000],  # Truncate long content
                    "url": entry.get("link", ""),
                    "published_at": published_str,
                    "known_at": article_known_at(published_str),
                    "content_hash": hash_data_record(name, title, published_str[:10]),
                }
                records.append(record)

        except Exception as e:
            logger.warning(f"RSS error for '{name}': {e}")
            continue

    logger.info(f"RSS feeds: fetched {len(records)} articles")
    return records


def fetch_and_store(
    store: DataStore,
    api_key: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> int:
    """Fetch from all news sources and store.

    Returns:
        Total records inserted.
    """
    all_records = []

    # NewsAPI (if key provided)
    if api_key:
        newsapi_records = fetch_newsapi(api_key, from_date, to_date)
        all_records.extend(newsapi_records)

    # RSS feeds (always available)
    rss_records = fetch_rss_feeds()
    all_records.extend(rss_records)

    if not all_records:
        return 0

    inserted = store.insert_articles(all_records)
    logger.info(f"Stored {inserted} news articles total")
    return inserted
