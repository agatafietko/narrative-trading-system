"""Portfolio constraints enforcement.

Applies position limits, sector concentration limits, turnover caps,
and other risk constraints to raw target weights.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.utils.logging import get_logger

logger = get_logger("portfolio.constraints")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def load_constraints() -> dict:
    """Load constraint parameters from config."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["constraints"]


def load_universe() -> dict:
    """Load universe with asset class info."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["universe"]


def apply_constraints(
    target_weights: dict[str, float],
    current_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Apply all portfolio constraints to target weights.

    Args:
        target_weights: Raw target weights from council/constructor.
        current_weights: Current portfolio weights (for turnover check).

    Returns:
        Constrained weights that satisfy all limits.
    """
    constraints = load_constraints()
    universe = load_universe()

    max_position = constraints["max_single_position"]
    max_equity = constraints["max_equity_concentration"]
    min_cash = constraints["min_cash_buffer"]
    max_turnover = constraints["max_turnover_per_rebalance"]

    weights = dict(target_weights)

    # 1. Cap individual positions
    for inst, w in weights.items():
        if abs(w) > max_position:
            logger.info(f"Capping {inst}: {w:.3f} -> {max_position:.3f}")
            weights[inst] = max_position if w > 0 else -max_position

    # 2. Cap equity concentration
    equity_instruments = [
        inst for inst, info in universe.items()
        if info.get("asset_class") == "equity"
    ]
    equity_weight = sum(weights.get(inst, 0) for inst in equity_instruments)

    if equity_weight > max_equity:
        scale = max_equity / equity_weight
        for inst in equity_instruments:
            if inst in weights:
                weights[inst] *= scale
        logger.info(f"Scaled equity concentration: {equity_weight:.3f} -> {max_equity:.3f}")

    # 3. Ensure total weight leaves room for cash buffer
    max_invested = 1.0 - min_cash
    total_weight = sum(abs(w) for w in weights.values())

    if total_weight > max_invested:
        scale = max_invested / total_weight
        weights = {k: v * scale for k, v in weights.items()}
        logger.info(f"Scaled total weight for cash buffer: {total_weight:.3f} -> {max_invested:.3f}")

    # 4. Cap turnover (if current weights provided)
    if current_weights is not None:
        total_turnover = sum(
            abs(weights.get(inst, 0) - current_weights.get(inst, 0))
            for inst in set(list(weights.keys()) + list(current_weights.keys()))
        )

        if total_turnover > max_turnover:
            # Scale changes toward current weights
            scale = max_turnover / total_turnover
            for inst in set(list(weights.keys()) + list(current_weights.keys())):
                current_w = current_weights.get(inst, 0)
                target_w = weights.get(inst, 0)
                delta = target_w - current_w
                weights[inst] = current_w + delta * scale

            logger.info(f"Capped turnover: {total_turnover:.3f} -> {max_turnover:.3f}")

    return weights


def compute_cash_weight(weights: dict[str, float]) -> float:
    """Compute implied cash weight."""
    return 1.0 - sum(abs(w) for w in weights.values())
