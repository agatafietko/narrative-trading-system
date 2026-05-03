#!/usr/bin/env python3
"""Fetch historical data for backtesting.

Usage:
    python scripts/fetch_historical_data.py [--start 2020-01-01] [--end 2024-12-31]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.data.fetchers import yfinance_fetcher, fred_fetcher
from src.state.store import DataStore
from src.utils.logging import setup_logging

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Fetch historical data")
    parser.add_argument("--start", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--skip-market", action="store_true", help="Skip market data")
    parser.add_argument("--skip-fred", action="store_true", help="Skip FRED data")
    args = parser.parse_args()

    logger = setup_logging("INFO")
    store = DataStore()

    logger.info(f"Fetching data from {args.start} to {args.end or 'today'}")

    # Fetch market data
    if not args.skip_market:
        logger.info("=" * 60)
        logger.info("Fetching market data (yfinance)...")
        logger.info("=" * 60)
        count = yfinance_fetcher.fetch_and_store(store, args.start, args.end)
        logger.info(f"Market data: {count} records stored")

    # Fetch FRED data
    if not args.skip_fred:
        fred_key = os.getenv("FRED_API_KEY")
        if not fred_key:
            logger.warning("FRED_API_KEY not set — skipping FRED data")
        else:
            logger.info("=" * 60)
            logger.info("Fetching FRED economic data...")
            logger.info("=" * 60)
            count = fred_fetcher.fetch_and_store(store, fred_key, args.start, args.end)
            logger.info(f"FRED data: {count} records stored")

    logger.info("=" * 60)
    logger.info("Data fetch complete.")


if __name__ == "__main__":
    main()
