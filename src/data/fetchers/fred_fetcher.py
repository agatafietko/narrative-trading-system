"""FRED (Federal Reserve Economic Data) fetcher.

Fetches economic indicators with proper known_at timestamps.
FRED provides release dates, which are critical for temporal discipline.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from src.state.store import DataStore
from src.utils.logging import get_logger
from src.utils.temporal import fred_release_known_at

logger = get_logger("fetcher.fred")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config"


def load_fred_config() -> list[dict]:
    """Load FRED series configuration."""
    with open(CONFIG_PATH / "data_sources.yaml") as f:
        config = yaml.safe_load(f)
    return config["fred"]["series"]


def fetch_fred_data(
    api_key: str,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> list[dict]:
    """Fetch all configured FRED series.

    Args:
        api_key: FRED API key.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD). Defaults to today.

    Returns:
        List of records with series_id, date, value, known_at.
    """
    from fredapi import Fred

    fred = Fred(api_key=api_key)
    series_config = load_fred_config()

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    all_records = []

    for series in series_config:
        series_id = series["id"]
        logger.info(f"Fetching FRED series: {series_id} ({series['name']})...")

        try:
            data = fred.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date,
            )

            if data is None or data.empty:
                logger.warning(f"No data for {series_id}")
                continue

            # Try to get release dates for proper known_at timestamps
            try:
                release_dates = fred.get_series_all_releases(series_id)
                # Build a map: observation_date -> first release date
                release_map = {}
                if release_dates is not None and not release_dates.empty:
                    for _, row in release_dates.iterrows():
                        obs_date = row.name.strftime("%Y-%m-%d") if hasattr(row.name, 'strftime') else str(row.name)
                        if obs_date not in release_map:
                            release_map[obs_date] = row.get("realtime_start", obs_date)
            except Exception:
                release_map = {}

            for date_idx, value in data.items():
                if pd.isna(value):
                    continue

                obs_date = date_idx.strftime("%Y-%m-%d")

                # Use release date if available, otherwise estimate
                if obs_date in release_map:
                    release_date = str(release_map[obs_date])
                    known_at = fred_release_known_at(release_date)
                else:
                    # For daily series (like yields), data is known same day
                    # For monthly/quarterly, add a standard publication lag
                    freq = series.get("frequency", "daily")
                    if freq == "daily":
                        known_at = fred_release_known_at(obs_date, "16:15")
                    elif freq == "monthly":
                        # Monthly data typically released ~2 weeks after month end
                        lag_date = (date_idx + pd.DateOffset(days=15)).strftime("%Y-%m-%d")
                        known_at = fred_release_known_at(lag_date)
                    else:  # quarterly
                        lag_date = (date_idx + pd.DateOffset(days=30)).strftime("%Y-%m-%d")
                        known_at = fred_release_known_at(lag_date)

                all_records.append({
                    "series_id": series_id,
                    "date": obs_date,
                    "value": float(value),
                    "known_at": known_at,
                    "revision_number": 0,
                })

            logger.info(f"  Fetched {len(data)} observations for {series_id}")

        except Exception as e:
            logger.error(f"Error fetching {series_id}: {e}")
            continue

    logger.info(f"Total FRED records: {len(all_records)}")
    return all_records


def fetch_and_store(
    store: DataStore,
    api_key: str,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> int:
    """Fetch FRED data and store in database.

    Returns:
        Number of records inserted.
    """
    records = fetch_fred_data(api_key, start_date, end_date)
    if not records:
        return 0
    inserted = store.insert_fred_data(records)
    logger.info(f"Inserted {inserted} FRED records")
    return inserted
