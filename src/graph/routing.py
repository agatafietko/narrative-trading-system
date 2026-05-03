"""Conditional routing functions for the LangGraph workflow.

These functions determine which node to visit next based on the current state.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.utils.logging import get_logger

logger = get_logger("graph.routing")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def _load_council_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["council"]


def check_consensus(state: dict) -> str:
    """Determine if the council has reached consensus.

    Routes to:
    - 'portfolio_constructor' if consensus reached (conviction >= threshold)
        or max rounds exceeded
    - 'strategist' for another debate round

    Returns:
        Name of the next node.
    """
    council_config = _load_council_config()
    threshold = council_config["consensus_threshold"]
    max_rounds = council_config["max_debate_rounds"]

    round_num = state.get("council_round", 0)
    decision = state.get("synthesizer_decision", {})
    conviction = decision.get("overall_conviction", 0.0)

    if round_num >= max_rounds:
        logger.info(
            f"[Routing] Max rounds ({max_rounds}) reached. "
            f"Proceeding with conviction={conviction:.2f}"
        )
        return "portfolio_constructor"

    if conviction >= threshold:
        logger.info(
            f"[Routing] Consensus reached: conviction={conviction:.2f} >= {threshold}"
        )
        return "portfolio_constructor"

    logger.info(
        f"[Routing] No consensus: conviction={conviction:.2f} < {threshold}. "
        f"Round {round_num}/{max_rounds}. Debating again."
    )
    return "strategist"
