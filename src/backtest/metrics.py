"""Performance metrics for backtesting.

Standard risk-adjusted metrics: Sharpe, Sortino, Calmar, max drawdown,
information ratio, hit rate, etc.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio."""
    excess = returns - risk_free_rate / 252
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(252))


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sortino ratio (only downside volatility)."""
    excess = returns - risk_free_rate / 252
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float(excess.mean() / downside.std() * np.sqrt(252))


def max_drawdown(nav_series: pd.Series) -> float:
    """Maximum drawdown as a negative fraction."""
    peak = nav_series.cummax()
    dd = (nav_series - peak) / peak
    return float(dd.min())


def calmar_ratio(returns: pd.Series, nav_series: pd.Series) -> float:
    """Calmar ratio = annualized return / |max drawdown|."""
    ann_return = returns.mean() * 252
    mdd = abs(max_drawdown(nav_series))
    if mdd == 0:
        return 0.0
    return float(ann_return / mdd)


def information_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
) -> float:
    """Information ratio vs benchmark."""
    active = returns - benchmark_returns
    if active.std() == 0:
        return 0.0
    return float(active.mean() / active.std() * np.sqrt(252))


def hit_rate(returns: pd.Series) -> float:
    """Fraction of periods with positive returns."""
    if len(returns) == 0:
        return 0.0
    return float((returns > 0).sum() / len(returns))


def total_return(nav_series: pd.Series) -> float:
    """Total return over the period."""
    if len(nav_series) < 2:
        return 0.0
    return float(nav_series.iloc[-1] / nav_series.iloc[0] - 1)


def annualized_return(returns: pd.Series) -> float:
    """Annualized return from daily returns."""
    if len(returns) == 0:
        return 0.0
    cumulative = (1 + returns).prod()
    years = len(returns) / 252
    if years == 0:
        return 0.0
    return float(cumulative ** (1 / years) - 1)


def annualized_volatility(returns: pd.Series) -> float:
    """Annualized volatility."""
    return float(returns.std() * np.sqrt(252))


def compute_all_metrics(
    nav_series: pd.Series,
    benchmark_nav: pd.Series | None = None,
    total_costs: float = 0.0,
) -> dict:
    """Compute a full suite of performance metrics.

    Args:
        nav_series: Portfolio NAV time series.
        benchmark_nav: Benchmark NAV time series (optional).
        total_costs: Total transaction costs incurred.

    Returns:
        Dict of all metrics.
    """
    returns = nav_series.pct_change().dropna()

    metrics = {
        "total_return": total_return(nav_series),
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "max_drawdown": max_drawdown(nav_series),
        "calmar_ratio": calmar_ratio(returns, nav_series),
        "hit_rate": hit_rate(returns),
        "total_costs": total_costs,
        "num_periods": len(returns),
    }

    if benchmark_nav is not None:
        bench_returns = benchmark_nav.pct_change().dropna()
        # Align
        common_idx = returns.index.intersection(bench_returns.index)
        if len(common_idx) > 0:
            metrics["information_ratio"] = information_ratio(
                returns.loc[common_idx], bench_returns.loc[common_idx]
            )
            metrics["benchmark_total_return"] = total_return(benchmark_nav)
            metrics["excess_return"] = metrics["total_return"] - metrics["benchmark_total_return"]

    return metrics
