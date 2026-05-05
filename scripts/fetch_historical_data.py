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
    # Defer heavy imports to main() so the module can be imported cheaply in tests
    from dotenv import load_dotenv
    from src.data.fetchers import yfinance_fetcher, fred_fetcher, finnhub_fetcher
    from src.state.store import DataStore
    from src.utils.logging import setup_logging

    load_dotenv()

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
