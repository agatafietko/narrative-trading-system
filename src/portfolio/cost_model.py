"""Transaction cost model.

Applies round-trip costs (30 bps) plus instrument-specific slippage.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.utils.logging import get_logger

logger = get_logger("portfolio.cost_model")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def load_cost_config() -> tuple[float, dict[str, int]]:
    """Load cost parameters from config.

    Returns:
        (round_trip_bps, instrument_slippage_bps)
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    round_trip_bps = config["costs"]["round_trip_bps"]
    universe = config["universe"]
    slippage = {inst: info.get("slippage_bps", 0) for inst, info in universe.items()}

    return round_trip_bps, slippage


def compute_trade_cost(
    instrument: str,
    dollar_amount: float,
) -> float:
    """Compute the total transaction cost for a trade.

    Args:
        instrument: Instrument name.
        dollar_amount: Absolute dollar value of the trade.

    Returns:
        Total cost in dollars.
    """
    round_trip_bps, slippage_map = load_cost_config()
    slippage_bps = slippage_map.get(instrument, 0)

    total_bps = round_trip_bps + slippage_bps
    cost = dollar_amount * (total_bps / 10_000)

    return cost


def compute_order_costs(
    orders: list[dict],
) -> list[dict]:
    """Add cost field to a list of trade orders.

    Args:
        orders: List of order dicts with 'instrument' and 'dollar_amount'.

    Returns:
        Same orders with 'cost' field added/updated.
    """
    for order in orders:
        order["cost"] = compute_trade_cost(
            order["instrument"],
            abs(order["dollar_amount"]),
        )
    return orders
