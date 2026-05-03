"""GDELT (Global Database of Events, Language, and Tone) fetcher.

Fetches event tone and theme data from the GDELT 2.0 API.
Used for macro event detection and global sentiment signals.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import requests

from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("fetcher.gdelt")

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_gdelt_tone(
    keywords: list[str] | None = None,
    lookback_days: int = 7,
) -> list[dict]:
    """Fetch GDELT tone data for finance-related themes.

    Uses the GDELT DOC 2.0 API to get article tone and volume
    for financial keywords.

    Args:
        keywords: Search keywords. Defaults to finance-related terms.
        lookback_days: How many days back to search.

    Returns:
        List of GDELT event records.
    """
    if keywords is None:
        keywords = [
            "federal reserve",
            "interest rate",
            "inflation",
            "recession",
            "stock market",
            "oil price",
            "gold price",
            "cryptocurrency",
        ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)

    records = []
    for keyword in keywords:
        try:
            resp = requests.get(
                GDELT_DOC_API,
                params={
                    "query": keyword,
                    "mode": "timelinetone",
                    "startdatetime": start_date.strftime("%Y%m%d%H%M%S"),
                    "enddatetime": end_date.strftime("%Y%m%d%H%M%S"),
                    "format": "json",
                },
                timeout=30,
            )

            if resp.status_code != 200:
                logger.warning(f"GDELT API error for '{keyword}': {resp.status_code}")
                continue

            data = resp.json()
            timeline = data.get("timeline", [])

            for series in timeline:
                for point in series.get("data", []):
                    date_str = point.get("date", "")
                    if not date_str:
                        continue

                    # GDELT dates are in YYYYMMDDHHMMSS format
                    try:
                        dt = datetime.strptime(date_str, "%Y%m%d%H%M%S")
                    except ValueError:
                        continue

                    records.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "themes": keyword,
                        "tone": float(point.get("value", 0)),
                        "num_articles": int(point.get("count", 0)) if "count" in point else 1,
                        "known_at": dt.isoformat(),
                    })

        except Exception as e:
            logger.warning(f"GDELT error for '{keyword}': {e}")
            continue

    logger.info(f"GDELT: fetched {len(records)} tone data points")
    return records


def fetch_and_store(store: DataStore, lookback_days: int = 7) -> int:
    """Fetch GDELT data and store in database."""
    records = fetch_gdelt_tone(lookback_days=lookback_days)

    if not records:
        return 0

    # Insert via raw SQL since we don't have a bulk insert for GDELT in store
    inserted = 0
    with store._connect() as conn:
        for rec in records:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO gdelt_events
                        (date, themes, tone, num_articles, known_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (rec["date"], rec["themes"], rec["tone"],
                     rec["num_articles"], rec["known_at"]),
                )
                inserted += 1
            except Exception:
                pass

    logger.info(f"Stored {inserted} GDELT records")
    return inserted
