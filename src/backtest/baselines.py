"""Baseline strategies for comparison.

Provides simple benchmark strategies that the multi-agent system
must outperform to demonstrate value:
- 60/40 (S&P 500 / US 10Y bonds)
- Equal weight across all instruments
- Random weights
"""

from __future__ import annotations

import random
from datetime import datetime

import numpy as np
import pandas as pd

from src.portfolio.cost_model import compute_trade_cost
from src.utils.logging import get_logger

logger = get_logger("backtest.baselines")


def run_buy_and_hold(
    prices: pd.DataFrame,
    weights: dict[str, float],
    initial_capital: float = 1_000_000,
) -> pd.Series:
    """Run a buy-and-hold strategy with fixed initial weights.

    Args:
        prices: DataFrame with columns = instruments, index = dates, values = adj_close.
        weights: instrument -> initial weight.
        initial_capital: Starting capital.

    Returns:
        NAV time series.
    """
    # Drop rows where any held instrument has NaN prices
    held_instruments = [inst for inst in weights if inst in prices.columns]
    clean_prices = prices.dropna(subset=held_instruments)

    if clean_prices.empty:
        return pd.Series([initial_capital], index=prices.index[:1], name="nav")

    # Compute initial shares
    first_prices = clean_prices.iloc[0]
    shares = {}
    for inst, w in weights.items():
        if inst in clean_prices.columns:
            dollar_alloc = initial_capital * w
            shares[inst] = dollar_alloc / first_prices[inst]

    # Compute NAV for each day
    nav = []
    for idx, row in clean_prices.iterrows():
        day_nav = sum(shares.get(inst, 0) * row.get(inst, 0) for inst in shares)
        # Add unallocated cash
        cash = initial_capital * (1 - sum(weights.values()))
        nav.append(day_nav + cash)

    return pd.Series(nav, index=clean_prices.index, name="nav")


def run_sixty_forty(
    prices: pd.DataFrame,
    initial_capital: float = 1_000_000,
) -> pd.Series:
    """60% S&P 500, 40% US 10Y bonds — buy and hold."""
    weights = {"SP500": 0.60, "US_10Y": 0.40}
    return run_buy_and_hold(prices, weights, initial_capital)


def run_equal_weight(
    prices: pd.DataFrame,
    initial_capital: float = 1_000_000,
) -> pd.Series:
    """Equal weight across all instruments — buy and hold."""
    instruments = [col for col in prices.columns]
    n = len(instruments)
    weight = 0.95 / n  # 5% cash
    weights = {inst: weight for inst in instruments}
    return run_buy_and_hold(prices, weights, initial_capital)


def run_random_weights(
    prices: pd.DataFrame,
    rebalance_dates: list,
    initial_capital: float = 1_000_000,
    seed: int = 42,
) -> pd.Series:
    """Random weights, rebalanced on given dates.

    Uses Dirichlet distribution for random weight generation.
    Applies transaction costs on rebalance.
    """
    rng = np.random.RandomState(seed)
    # Forward-fill NaN prices (weekends/holidays for some instruments)
    prices = prices.ffill()
    instruments = list(prices.columns)
    n = len(instruments)

    nav = initial_capital
    current_weights = {}
    nav_series = []

    for i, date in enumerate(prices.index):
        # Compute daily return
        if i > 0 and current_weights:
            prev_prices = prices.iloc[i - 1]
            curr_prices = prices.iloc[i]
            daily_return = sum(
                current_weights.get(inst, 0) * (curr_prices[inst] / prev_prices[inst] - 1)
                for inst in instruments
                if inst in current_weights
                and pd.notna(prev_prices[inst]) and pd.notna(curr_prices[inst])
                and prev_prices[inst] != 0
            )
            nav *= (1 + daily_return)

        # Rebalance on specified dates
        if date in rebalance_dates:
            # Generate random weights (Dirichlet ensures they sum to ~0.95)
            raw = rng.dirichlet(np.ones(n))
            new_weights = {inst: float(w * 0.95) for inst, w in zip(instruments, raw)}

            # Apply transaction costs
            if current_weights:
                for inst in instruments:
                    delta = abs(new_weights.get(inst, 0) - current_weights.get(inst, 0))
                    cost = compute_trade_cost(inst, delta * nav)
                    nav -= cost

            current_weights = new_weights

        nav_series.append(nav)

    return pd.Series(nav_series, index=prices.index, name="nav")
