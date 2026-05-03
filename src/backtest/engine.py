"""Backtest Engine — the main simulation loop.

Iterates over trading dates, invokes the LangGraph workflow (or a simpler
pipeline for baselines), tracks NAV, and stores results.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

from src.agents.execution.order_manager import apply_orders_to_portfolio, generate_orders
from src.backtest.metrics import compute_all_metrics
from src.state.store import DataStore
from src.utils.logging import get_logger
from src.utils.reproducibility import generate_run_id, set_global_seed

logger = get_logger("backtest.engine")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def load_backtest_config() -> dict:
    """Load backtest parameters from config."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["backtest"]


def get_rebalance_dates(
    start_date: str,
    end_date: str,
    rebalance_day: int = 4,  # Friday
) -> list[datetime]:
    """Generate list of rebalance dates (every Friday in range)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    dates = []
    current = start
    while current <= end:
        if current.weekday() == rebalance_day:
            dates.append(current)
        current += timedelta(days=1)

    return dates


class BacktestEngine:
    """Main backtesting engine.

    Iterates over rebalance dates, calls the strategy function for each date,
    generates trade orders, and tracks portfolio performance.
    """

    def __init__(
        self,
        store: DataStore,
        strategy_fn: Callable[[datetime, dict[str, float], float, DataStore], dict[str, float]],
        run_id: str | None = None,
        seed: int = 42,
        start_date: str | None = None,
        end_date: str | None = None,
    ):
        """
        Args:
            store: DataStore for point-in-time data access.
            strategy_fn: Function that takes (as_of, current_weights, nav, store)
                         and returns target_weights dict.
            run_id: Unique run identifier. Auto-generated if None.
            seed: Random seed for reproducibility.
            start_date: Override config start date (YYYY-MM-DD).
            end_date: Override config end date (YYYY-MM-DD).
        """
        self.store = store
        self.strategy_fn = strategy_fn
        self.run_id = run_id or generate_run_id()
        self.seed = seed

        config = load_backtest_config()
        self.initial_capital = config["initial_capital"]
        self.start_date = start_date or config["start_date"]
        self.end_date = end_date or config["end_date"]
        self.rebalance_day = config["rebalance_day"]

    def run(self) -> BacktestResult:
        """Execute the backtest.

        Returns:
            BacktestResult with NAV history and metrics.
        """
        set_global_seed(self.seed)

        logger.info(f"Starting backtest: {self.run_id}")
        logger.info(f"Period: {self.start_date} to {self.end_date}")
        logger.info(f"Initial capital: ${self.initial_capital:,.0f}")

        rebalance_dates = get_rebalance_dates(
            self.start_date, self.end_date, self.rebalance_day
        )
        logger.info(f"Rebalance dates: {len(rebalance_dates)} Fridays")

        # Initialize state
        nav = float(self.initial_capital)
        current_weights: dict[str, float] = {}
        total_costs = 0.0

        # Track daily NAV (approximate between rebalances using weights + prices)
        nav_history: list[dict] = []
        all_orders: list[dict] = []

        # Get all market data for daily NAV tracking
        market_data = self.store.get_market_data_as_of(
            datetime.strptime(self.end_date, "%Y-%m-%d"),
            lookback_days=252 * 5,
        )

        if market_data.empty:
            logger.error("No market data available. Run fetch_historical_data.py first.")
            return BacktestResult(
                run_id=self.run_id,
                nav_series=pd.Series(dtype=float),
                metrics={},
                orders=[],
                total_costs=0,
            )

        # Pivot to get price matrix
        price_matrix = market_data.pivot_table(
            index="date", columns="instrument", values="adj_close"
        ).sort_index()

        prev_prices = None

        for date_idx, row in price_matrix.iterrows():
            current_date = pd.Timestamp(date_idx)

            # Update NAV based on daily price changes
            if prev_prices is not None and current_weights:
                daily_pnl = 0.0
                for inst, weight in current_weights.items():
                    if inst in row.index and inst in prev_prices.index:
                        prev_p = prev_prices[inst]
                        curr_p = row[inst]
                        if pd.notna(prev_p) and pd.notna(curr_p) and prev_p > 0:
                            daily_pnl += weight * (curr_p / prev_p - 1)
                nav *= (1 + daily_pnl)

            prev_prices = row

            # Check if this is a rebalance date
            as_of_dt = current_date.to_pydatetime()
            is_rebalance = any(
                abs((as_of_dt - rd).total_seconds()) < 86400
                for rd in rebalance_dates
            )

            if is_rebalance:
                logger.info(f"Rebalancing on {current_date.date()} | NAV: ${nav:,.0f}")

                # Call strategy
                target_weights = self.strategy_fn(
                    as_of_dt, current_weights, nav, self.store
                )

                # Generate and execute orders
                orders = generate_orders(current_weights, target_weights, nav)
                if orders:
                    current_weights, nav = apply_orders_to_portfolio(
                        current_weights, orders, nav
                    )
                    period_cost = sum(o["cost"] for o in orders)
                    total_costs += period_cost
                    all_orders.extend(orders)

                    # Store orders and snapshot
                    self.store.store_trade_orders(
                        self.run_id, current_date.isoformat(), orders
                    )

                self.store.store_portfolio_snapshot(
                    self.run_id,
                    current_date.isoformat(),
                    nav,
                    current_weights,
                    1.0 - sum(abs(w) for w in current_weights.values()),
                    total_costs,
                )

            nav_history.append({
                "date": current_date,
                "nav": nav,
            })

        # Build NAV series
        nav_df = pd.DataFrame(nav_history)
        if nav_df.empty:
            nav_series = pd.Series(dtype=float)
        else:
            nav_series = nav_df.set_index("date")["nav"]

        # Compute metrics
        metrics = compute_all_metrics(nav_series, total_costs=total_costs)

        logger.info("=" * 60)
        logger.info(f"Backtest complete: {self.run_id}")
        logger.info(f"Final NAV: ${nav:,.0f}")
        logger.info(f"Total return: {metrics.get('total_return', 0):.2%}")
        logger.info(f"Sharpe ratio: {metrics.get('sharpe_ratio', 0):.2f}")
        logger.info(f"Max drawdown: {metrics.get('max_drawdown', 0):.2%}")
        logger.info(f"Total costs: ${total_costs:,.0f}")
        logger.info("=" * 60)

        return BacktestResult(
            run_id=self.run_id,
            nav_series=nav_series,
            metrics=metrics,
            orders=all_orders,
            total_costs=total_costs,
        )


class BacktestResult:
    """Container for backtest results."""

    def __init__(
        self,
        run_id: str,
        nav_series: pd.Series,
        metrics: dict,
        orders: list[dict],
        total_costs: float,
    ):
        self.run_id = run_id
        self.nav_series = nav_series
        self.metrics = metrics
        self.orders = orders
        self.total_costs = total_costs

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Run ID: {self.run_id}",
            f"Total Return: {self.metrics.get('total_return', 0):.2%}",
            f"Annualized Return: {self.metrics.get('annualized_return', 0):.2%}",
            f"Annualized Vol: {self.metrics.get('annualized_volatility', 0):.2%}",
            f"Sharpe Ratio: {self.metrics.get('sharpe_ratio', 0):.2f}",
            f"Sortino Ratio: {self.metrics.get('sortino_ratio', 0):.2f}",
            f"Max Drawdown: {self.metrics.get('max_drawdown', 0):.2%}",
            f"Calmar Ratio: {self.metrics.get('calmar_ratio', 0):.2f}",
            f"Hit Rate: {self.metrics.get('hit_rate', 0):.2%}",
            f"Total Costs: ${self.total_costs:,.0f}",
            f"Num Trades: {len(self.orders)}",
        ]
        return "\n".join(lines)
