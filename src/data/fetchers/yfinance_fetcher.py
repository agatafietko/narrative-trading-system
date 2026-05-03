"""Yahoo Finance data fetcher.

Fetches historical OHLCV data for all instruments in the universe.
Each record gets a known_at timestamp = market close + 15 min buffer.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

from src.state.store import DataStore
from src.utils.logging import get_logger
from src.utils.temporal import market_close_known_at

logger = get_logger("fetcher.yfinance")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "settings.yaml"


def load_universe() -> dict[str, dict]:
    """Load the investment universe from config."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["universe"]


def fetch_market_data(
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> pd.DataFrame:
    """Fetch OHLCV data for all instruments in the universe.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD). Defaults to today.

    Returns:
        DataFrame with columns: instrument, ticker, date, open, high, low,
        close, adj_close, volume, known_at
    """
    universe = load_universe()
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    all_records = []

    for instrument_name, info in universe.items():
        ticker = info["ticker"]
        logger.info(f"Fetching {instrument_name} ({ticker})...")

        try:
            data = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                auto_adjust=False,
                progress=False,
            )

            if data.empty:
                logger.warning(f"No data returned for {ticker}")
                continue

            # Handle MultiIndex columns from yfinance
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            for date_idx, row in data.iterrows():
                trade_date = date_idx.strftime("%Y-%m-%d")
                all_records.append({
                    "instrument": instrument_name,
                    "ticker": ticker,
                    "date": trade_date,
                    "open": float(row.get("Open", 0)),
                    "high": float(row.get("High", 0)),
                    "low": float(row.get("Low", 0)),
                    "close": float(row.get("Close", 0)),
                    "adj_close": float(row.get("Adj Close", row.get("Close", 0))),
                    "volume": int(row.get("Volume", 0)),
                    "known_at": market_close_known_at(trade_date),
                })

            logger.info(f"  Fetched {len(data)} rows for {ticker}")

        except Exception as e:
            logger.error(f"Error fetching {ticker}: {e}")
            continue

    df = pd.DataFrame(all_records)
    logger.info(f"Total records fetched: {len(df)}")
    return df


def fetch_and_store(
    store: DataStore,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> int:
    """Fetch market data and store in the database.

    Returns:
        Number of records inserted.
    """
    df = fetch_market_data(start_date, end_date)
    if df.empty:
        return 0
    records = df.to_dict("records")
    inserted = store.insert_market_data(records)
    logger.info(f"Inserted {inserted} market data records")
    return inserted
