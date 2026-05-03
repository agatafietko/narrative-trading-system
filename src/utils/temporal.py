"""Temporal discipline utilities.

All data access in the system must respect point-in-time constraints.
These helpers ensure no look-ahead bias.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

# US Eastern timezone offset (simplified; production would use pytz/zoneinfo)
ET_OFFSET = timezone(timedelta(hours=-5))

# Market close + settlement buffer
MARKET_CLOSE = time(16, 0)
SETTLEMENT_BUFFER_MINUTES = 15


def market_close_known_at(trade_date: str) -> str:
    """Return the known_at timestamp for end-of-day market data.

    Market data for a given trade date becomes known at
    4:00 PM ET + 15 minute settlement buffer.
    """
    dt = datetime.strptime(trade_date, "%Y-%m-%d")
    close_dt = datetime.combine(
        dt.date(),
        MARKET_CLOSE,
        tzinfo=ET_OFFSET,
    ) + timedelta(minutes=SETTLEMENT_BUFFER_MINUTES)
    return close_dt.isoformat()


def fred_release_known_at(release_date: str, release_time: str = "08:30") -> str:
    """Return known_at for a FRED data release.

    Most FRED releases happen at 8:30 AM ET on the release date.
    """
    dt = datetime.strptime(f"{release_date} {release_time}", "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=ET_OFFSET).isoformat()


def article_known_at(published_at: str) -> str:
    """Articles are known at their publication time."""
    # Handle various ISO formats
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(published_at, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    # Fallback: return as-is
    return published_at


def is_available_as_of(known_at: str, as_of: datetime) -> bool:
    """Check if a data point was available at the given point in time."""
    known_dt = datetime.fromisoformat(known_at)
    if known_dt.tzinfo is None:
        known_dt = known_dt.replace(tzinfo=timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return known_dt <= as_of
