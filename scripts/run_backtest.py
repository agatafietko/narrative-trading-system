#!/usr/bin/env python3
"""Run a backtest with a specified strategy.

Usage:
    python scripts/run_backtest.py --strategy technical_momentum
    python scripts/run_backtest.py --strategy equal_weight
    python scripts/run_backtest.py --strategy sixty_forty
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.execution.portfolio_constructor import (
    construct_equal_weight,
    construct_sixty_forty,
)
from src.agents.gatherers.market_technician import generate_signal
from src.backtest.engine import BacktestEngine
from src.portfolio.constraints import apply_constraints
from src.state.store import DataStore
from src.utils.logging import setup_logging


def technical_momentum_strategy(
    as_of: datetime,
    current_weights: dict[str, float],
    nav: float,
    store: DataStore,
) -> dict[str, float]:
    """Simple momentum strategy using only technical signals.

    Uses trend direction and RSI to generate weights.
    This serves as the deterministic baseline for the paper.
    """
    market_data = store.get_market_data_as_of(as_of, lookback_days=252)
    if market_data.empty:
        return current_weights

    signal = generate_signal(market_data, as_of)
    instruments = signal.payload.get("instruments", {})

    raw_weights = {}
    for inst, analysis in instruments.items():
        if isinstance(analysis, dict) and "error" not in analysis:
            trend = analysis.get("trend", {})
            rsi = analysis.get("rsi", 50)
            momentum = analysis.get("momentum", {})

            # Simple scoring: trend alignment + RSI + momentum
            score = 0.0

            # Trend score
            trend_dir = trend.get("trend", "sideways")
            if "strong_uptrend" in trend_dir:
                score += 2.0
            elif "uptrend" in trend_dir:
                score += 1.0
            elif "strong_downtrend" in trend_dir:
                score -= 2.0
            elif "downtrend" in trend_dir:
                score -= 1.0

            # RSI score (contrarian: oversold = buy, overbought = sell)
            if rsi < 30:
                score += 1.0
            elif rsi > 70:
                score -= 1.0

            # 3-month momentum
            mom_3m = momentum.get("return_3m")
            if mom_3m is not None:
                score += mom_3m / 10  # Scale down

            raw_weights[inst] = max(score, 0)  # Long only

    # Normalize to sum to 0.95
    total = sum(raw_weights.values())
    if total > 0:
        raw_weights = {k: (v / total) * 0.95 for k, v in raw_weights.items()}
    else:
        # Fallback to equal weight if no positive signals
        n = len(instruments)
        raw_weights = {k: 0.95 / n for k in instruments}

    return apply_constraints(raw_weights, current_weights)


def equal_weight_strategy(
    as_of: datetime,
    current_weights: dict[str, float],
    nav: float,
    store: DataStore,
) -> dict[str, float]:
    """Static equal weight (only rebalances to maintain equal weights)."""
    return construct_equal_weight()


def sixty_forty_strategy(
    as_of: datetime,
    current_weights: dict[str, float],
    nav: float,
    store: DataStore,
) -> dict[str, float]:
    """Static 60/40 strategy."""
    return construct_sixty_forty()


STRATEGIES = {
    "technical_momentum": technical_momentum_strategy,
    "equal_weight": equal_weight_strategy,
    "sixty_forty": sixty_forty_strategy,
}


def main():
    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument(
        "--strategy",
        choices=list(STRATEGIES.keys()),
        default="technical_momentum",
        help="Strategy to backtest",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    logger = setup_logging("INFO")
    store = DataStore()

    strategy_fn = STRATEGIES[args.strategy]
    logger.info(f"Running backtest with strategy: {args.strategy}")

    engine = BacktestEngine(
        store=store,
        strategy_fn=strategy_fn,
        seed=args.seed,
    )

    result = engine.run()

    print("\n" + "=" * 60)
    print(f"BACKTEST RESULTS: {args.strategy}")
    print("=" * 60)
    print(result.summary())
    print("=" * 60)


if __name__ == "__main__":
    main()
