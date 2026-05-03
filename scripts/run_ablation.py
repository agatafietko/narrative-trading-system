#!/usr/bin/env python3
"""Run all ablation experiments.

Executes each variant of the system and collects comparative metrics.

Usage:
    python scripts/run_ablation.py [--variants full,minimal,no_narrative]
    python scripts/run_ablation.py --baselines-only
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.engine import BacktestEngine, get_rebalance_dates, load_backtest_config
from src.backtest.baselines import run_sixty_forty, run_equal_weight, run_random_weights
from src.backtest.metrics import compute_all_metrics
from src.graph.workflow import get_graph
from src.state.store import DataStore
from src.utils.logging import setup_logging
from src.utils.reproducibility import generate_run_id, set_global_seed


def run_graph_strategy(graph_variant: str):
    """Create a strategy function that uses a LangGraph workflow."""

    def strategy_fn(as_of, current_weights, nav, store):
        graph = get_graph(graph_variant)
        initial_state = {
            "run_id": generate_run_id(),
            "as_of": as_of,
            "current_portfolio": current_weights,
            "nav": nav,
            "signals": [],
            "council_round": 0,
        }

        result = graph.invoke(initial_state)
        return result.get("target_weights", current_weights)

    return strategy_fn


def run_baseline_experiments(store: DataStore) -> dict[str, dict]:
    """Run all deterministic baseline experiments."""
    config = load_backtest_config()

    # Get price data
    end_dt = datetime.strptime(config["end_date"], "%Y-%m-%d")
    market_data = store.get_market_data_as_of(end_dt, lookback_days=252 * 5)

    if market_data.empty:
        print("ERROR: No market data. Run scripts/fetch_historical_data.py first.")
        return {}

    # Pivot to price matrix and forward-fill gaps (BTC trades weekends, equities don't)
    prices = market_data.pivot_table(
        index="date", columns="instrument", values="adj_close"
    ).sort_index().ffill().dropna()

    results = {}

    # 60/40
    print("\n--- Running 60/40 Baseline ---")
    nav_6040 = run_sixty_forty(prices, config["initial_capital"])
    results["sixty_forty"] = compute_all_metrics(nav_6040)
    print(f"  Total return: {results['sixty_forty']['total_return']:.2%}")
    print(f"  Sharpe: {results['sixty_forty']['sharpe_ratio']:.2f}")

    # Equal weight
    print("\n--- Running Equal Weight Baseline ---")
    nav_ew = run_equal_weight(prices, config["initial_capital"])
    results["equal_weight"] = compute_all_metrics(nav_ew)
    print(f"  Total return: {results['equal_weight']['total_return']:.2%}")
    print(f"  Sharpe: {results['equal_weight']['sharpe_ratio']:.2f}")

    # Random
    print("\n--- Running Random Baseline ---")
    rebalance_dates = get_rebalance_dates(
        config["start_date"], config["end_date"], config["rebalance_day"]
    )
    rebalance_idx = pd.DatetimeIndex([d for d in rebalance_dates])
    nav_random = run_random_weights(prices, rebalance_idx, config["initial_capital"])
    results["random"] = compute_all_metrics(nav_random)
    print(f"  Total return: {results['random']['total_return']:.2%}")
    print(f"  Sharpe: {results['random']['sharpe_ratio']:.2f}")

    return results


def run_technical_momentum_experiment(store: DataStore) -> dict:
    """Run the technical momentum baseline using the backtest engine."""
    from scripts.run_backtest import technical_momentum_strategy

    engine = BacktestEngine(
        store=store,
        strategy_fn=technical_momentum_strategy,
        run_id=f"ablation_technical_{generate_run_id()}",
    )
    result = engine.run()
    return result.metrics


def print_comparison_table(all_results: dict[str, dict]):
    """Print a formatted comparison table of all experiments."""
    metrics_to_show = [
        ("total_return", "Total Return", ".2%"),
        ("annualized_return", "Ann. Return", ".2%"),
        ("annualized_volatility", "Ann. Vol", ".2%"),
        ("sharpe_ratio", "Sharpe", ".2f"),
        ("sortino_ratio", "Sortino", ".2f"),
        ("max_drawdown", "Max DD", ".2%"),
        ("calmar_ratio", "Calmar", ".2f"),
        ("hit_rate", "Hit Rate", ".2%"),
    ]

    # Header
    variants = list(all_results.keys())
    header = f"{'Metric':<18}" + "".join(f"{v:<16}" for v in variants)
    print("\n" + "=" * len(header))
    print("ABLATION RESULTS COMPARISON")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for key, label, fmt in metrics_to_show:
        row = f"{label:<18}"
        for variant in variants:
            val = all_results[variant].get(key, 0)
            formatted = f"{val:{fmt}}"
            row += f"{formatted:<16}"
        print(row)

    print("=" * len(header))


def main():
    parser = argparse.ArgumentParser(description="Run ablation experiments")
    parser.add_argument(
        "--variants",
        default="baselines,technical_momentum",
        help="Comma-separated list of variants to run",
    )
    parser.add_argument("--baselines-only", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--start",
        default=None,
        metavar="YYYY-MM-DD",
        help="Override backtest start date. Use this to run a short recent window "
             "instead of the full 2021-2024 academic period.",
    )
    parser.add_argument(
        "--end",
        default=None,
        metavar="YYYY-MM-DD",
        help="Override backtest end date (default: today).",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=None,
        metavar="N",
        help="Shorthand: run only the last N weeks. Sets --start to N weeks ago "
             "and --end to today. A value of 8 gives ~50 LLM calls (~$1, ~2 min).",
    )
    args = parser.parse_args()

    # Resolve date overrides
    from datetime import date, timedelta
    start_override = args.start
    end_override = args.end
    if args.weeks:
        end_override = end_override or date.today().strftime("%Y-%m-%d")
        start_override = (
            datetime.strptime(end_override, "%Y-%m-%d").date()
            - timedelta(weeks=args.weeks)
        ).strftime("%Y-%m-%d")
    if start_override or end_override:
        print(f"Date override: {start_override or 'config'} → {end_override or 'config'}")

    logger = setup_logging("INFO")
    set_global_seed(args.seed)
    store = DataStore()

    all_results = {}

    # Always run baselines
    print("\n" + "=" * 60)
    print("RUNNING BASELINE EXPERIMENTS")
    print("=" * 60)
    baseline_results = run_baseline_experiments(store)
    all_results.update(baseline_results)

    if not args.baselines_only:
        variants = [v.strip() for v in args.variants.split(",")]

        if "technical_momentum" in variants:
            print("\n" + "=" * 60)
            print("RUNNING TECHNICAL MOMENTUM BASELINE")
            print("=" * 60)
            all_results["tech_momentum"] = run_technical_momentum_experiment(store)

        # LLM-powered variants (these cost money)
        for variant in variants:
            if variant in ("baselines", "technical_momentum"):
                continue
            if variant in ("full", "minimal", "no_narrative"):
                print(f"\n{'='*60}")
                print(f"RUNNING GRAPH VARIANT: {variant}")
                print(f"{'='*60}")

                strategy_fn = run_graph_strategy(variant)
                engine = BacktestEngine(
                    store=store,
                    strategy_fn=strategy_fn,
                    run_id=f"ablation_{variant}_{generate_run_id()}",
                    start_date=start_override,
                    end_date=end_override,
                )
                result = engine.run()
                all_results[variant] = result.metrics

    # Print comparison
    if all_results:
        print_comparison_table(all_results)

        # Save to file
        output_path = Path("data/ablation_results.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
