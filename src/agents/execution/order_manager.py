"""Order Manager — converts portfolio weight changes into trade orders.

Deterministic module (no LLM). Computes deltas between current and target
weights, applies the transaction cost model, and filters trivial rebalances.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.portfolio.cost_model import compute_trade_cost
from src.utils.logging import get_logger

logger = get_logger("agent.order_manager")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "settings.yaml"


def load_min_trade_threshold() -> float:
    """Load minimum trade threshold from config."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["constraints"]["min_trade_threshold"]


def generate_orders(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    nav: float,
) -> list[dict]:
    """Generate trade orders from weight deltas.

    Args:
        current_weights: Current instrument -> weight.
        target_weights: Target instrument -> weight.
        nav: Current net asset value.

    Returns:
        List of trade order dicts.
    """
    min_threshold = load_min_trade_threshold()
    all_instruments = set(list(current_weights.keys()) + list(target_weights.keys()))

    orders = []
    total_cost = 0.0

    for inst in sorted(all_instruments):
        current_w = current_weights.get(inst, 0.0)
        target_w = target_weights.get(inst, 0.0)
        delta = target_w - current_w

        # Skip trivial rebalances
        if abs(delta) < min_threshold:
            continue

        dollar_amount = abs(delta) * nav
        cost = compute_trade_cost(inst, dollar_amount)
        total_cost += cost

        order = {
            "instrument": inst,
            "direction": "buy" if delta > 0 else "sell",
            "weight_delta": round(delta, 6),
            "dollar_amount": round(dollar_amount, 2),
            "cost": round(cost, 2),
        }
        orders.append(order)
        logger.info(
            f"  {order['direction'].upper()} {inst}: "
            f"delta={delta:+.3f}, ${dollar_amount:,.0f}, cost=${cost:,.2f}"
        )

    logger.info(f"Total orders: {len(orders)}, total cost: ${total_cost:,.2f}")
    return orders


def apply_orders_to_portfolio(
    current_weights: dict[str, float],
    orders: list[dict],
    nav: float,
) -> tuple[dict[str, float], float]:
    """Apply trade orders to update portfolio weights and NAV.

    Returns:
        (new_weights, new_nav) after deducting costs.
    """
    new_weights = dict(current_weights)
    total_cost = sum(o["cost"] for o in orders)

    for order in orders:
        inst = order["instrument"]
        new_weights[inst] = new_weights.get(inst, 0.0) + order["weight_delta"]

    # Remove instruments with ~zero weight
    new_weights = {k: v for k, v in new_weights.items() if abs(v) >= 0.001}

    # Deduct costs from NAV
    new_nav = nav - total_cost

    return new_weights, new_nav
