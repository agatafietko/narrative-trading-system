"""Risk management utilities.

Volatility scaling, drawdown protection, and risk-parity helpers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.logging import get_logger

logger = get_logger("portfolio.risk")


def inverse_volatility_weights(
    returns: pd.DataFrame,
    lookback: int = 60,
) -> dict[str, float]:
    """Compute inverse-volatility weights.

    Args:
        returns: DataFrame of daily returns (columns = instruments).
        lookback: Lookback window for vol estimation.

    Returns:
        instrument -> weight (sums to 1.0)
    """
    recent = returns.tail(lookback)
    vols = recent.std() * np.sqrt(252)

    # Inverse vol (handle zero vol)
    inv_vol = 1.0 / vols.replace(0, np.inf)
    inv_vol = inv_vol.replace(np.inf, 0)

    total = inv_vol.sum()
    if total == 0:
        # Equal weight fallback
        n = len(returns.columns)
        return {col: 1.0 / n for col in returns.columns}

    weights = (inv_vol / total).to_dict()
    return weights


def compute_drawdown(nav_series: pd.Series) -> pd.Series:
    """Compute drawdown series from NAV."""
    peak = nav_series.cummax()
    drawdown = (nav_series - peak) / peak
    return drawdown


def max_drawdown(nav_series: pd.Series) -> float:
    """Compute maximum drawdown."""
    dd = compute_drawdown(nav_series)
    return float(dd.min())


def scale_by_conviction(
    target_weights: dict[str, float],
    current_weights: dict[str, float],
    conviction: float,
) -> dict[str, float]:
    """Blend target weights with current weights based on conviction.

    Low conviction (close to 0) = stay near current portfolio.
    High conviction (close to 1) = move fully to target.

    Args:
        target_weights: Desired portfolio weights.
        current_weights: Current portfolio weights.
        conviction: Council conviction score (0.0 to 1.0).

    Returns:
        Blended weights.
    """
    all_instruments = set(list(target_weights.keys()) + list(current_weights.keys()))
    blended = {}

    for inst in all_instruments:
        current_w = current_weights.get(inst, 0.0)
        target_w = target_weights.get(inst, 0.0)
        blended[inst] = current_w + conviction * (target_w - current_w)

    return blended
