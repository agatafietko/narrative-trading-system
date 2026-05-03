"""Portfolio Constructor — translates council decisions into target weights.

Deterministic module (no LLM). Takes the Synthesizer's output and produces
constrained, risk-scaled portfolio weights.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.portfolio.constraints import apply_constraints, compute_cash_weight
from src.portfolio.risk import scale_by_conviction
from src.utils.logging import get_logger

logger = get_logger("agent.portfolio_constructor")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "settings.yaml"


def load_universe_instruments() -> list[str]:
    """Get list of instrument names from config."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return list(config["universe"].keys())


def construct_portfolio(
    synthesizer_decision: dict,
    current_portfolio: dict[str, float],
) -> dict[str, float]:
    """Construct target portfolio weights from council decision.

    Args:
        synthesizer_decision: The Synthesizer's CouncilVote dict, containing
            'views' (list of InstrumentView dicts) and 'overall_conviction'.
        current_portfolio: Current instrument -> weight mapping.

    Returns:
        Constrained target weights.
    """
    conviction = synthesizer_decision.get("overall_conviction", 0.5)
    views = synthesizer_decision.get("views", [])

    # Extract raw target weights from council views
    raw_weights = {}
    for view in views:
        inst = view["instrument"]
        raw_weights[inst] = view["target_weight"]

    logger.info(f"Council conviction: {conviction:.2f}")
    logger.info(f"Raw target weights: {raw_weights}")

    # Scale by conviction (blend with current portfolio)
    blended = scale_by_conviction(raw_weights, current_portfolio, conviction)

    # Apply all constraints
    constrained = apply_constraints(blended, current_portfolio)

    cash = compute_cash_weight(constrained)
    logger.info(f"Constrained weights: {constrained}")
    logger.info(f"Cash weight: {cash:.3f}")

    return constrained


def construct_equal_weight() -> dict[str, float]:
    """Construct equal-weight portfolio (baseline)."""
    instruments = load_universe_instruments()
    n = len(instruments)
    # Leave 5% cash
    weight = 0.95 / n
    return {inst: weight for inst in instruments}


def construct_sixty_forty() -> dict[str, float]:
    """Construct 60/40 portfolio (baseline)."""
    return {
        "SP500": 0.60,
        "US_10Y": 0.40,
    }
