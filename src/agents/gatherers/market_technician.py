"""Market Technician — deterministic technical analysis agent.

No LLM calls. Computes standard technical indicators for each instrument.
This is intentionally deterministic to serve as an ablation baseline:
it isolates "does the technical data help?" from "does the LLM help?"
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from src.state.schema import Signal
from src.utils.logging import get_logger

logger = get_logger("agent.market_technician")


def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """Compute Relative Strength Index."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()

    if loss.iloc[-1] == 0:
        return 100.0

    rs = gain.iloc[-1] / loss.iloc[-1]
    return float(100 - (100 / (1 + rs)))


def compute_macd(prices: pd.Series) -> dict:
    """Compute MACD (12, 26, 9)."""
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    return {
        "macd": float(macd_line.iloc[-1]),
        "signal": float(signal_line.iloc[-1]),
        "histogram": float(histogram.iloc[-1]),
        "crossover": "bullish" if histogram.iloc[-1] > 0 and histogram.iloc[-2] <= 0
                     else "bearish" if histogram.iloc[-1] < 0 and histogram.iloc[-2] >= 0
                     else "none",
    }


def compute_bollinger_bands(prices: pd.Series, period: int = 20) -> dict:
    """Compute Bollinger Bands."""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std

    current_price = prices.iloc[-1]
    bandwidth = float((upper.iloc[-1] - lower.iloc[-1]) / sma.iloc[-1])

    # Position within bands: 0 = at lower band, 1 = at upper band
    band_position = float(
        (current_price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])
    ) if upper.iloc[-1] != lower.iloc[-1] else 0.5

    return {
        "upper": float(upper.iloc[-1]),
        "middle": float(sma.iloc[-1]),
        "lower": float(lower.iloc[-1]),
        "bandwidth": bandwidth,
        "band_position": band_position,
    }


def compute_trend(prices: pd.Series) -> dict:
    """Determine trend direction using moving averages."""
    sma_20 = prices.rolling(20).mean().iloc[-1]
    sma_50 = prices.rolling(50).mean().iloc[-1]
    sma_200 = prices.rolling(200).mean().iloc[-1] if len(prices) >= 200 else sma_50

    current = prices.iloc[-1]

    # Trend classification
    if current > sma_20 > sma_50:
        trend = "strong_uptrend"
    elif current > sma_50:
        trend = "uptrend"
    elif current < sma_20 < sma_50:
        trend = "strong_downtrend"
    elif current < sma_50:
        trend = "downtrend"
    else:
        trend = "sideways"

    return {
        "trend": trend,
        "price_vs_sma20": float((current / sma_20 - 1) * 100),
        "price_vs_sma50": float((current / sma_50 - 1) * 100),
        "sma20_vs_sma50": float((sma_20 / sma_50 - 1) * 100),
        "golden_cross": bool(sma_50 > sma_200 and sma_20 > sma_50),
        "death_cross": bool(sma_50 < sma_200 and sma_20 < sma_50),
    }


def compute_volatility(prices: pd.Series, period: int = 20) -> dict:
    """Compute realized volatility metrics."""
    returns = prices.pct_change().dropna()

    if len(returns) < period:
        return {"realized_vol": 0.0, "vol_regime": "unknown", "vol_percentile": 50.0}

    recent_vol = returns.tail(period).std() * np.sqrt(252)
    long_vol = returns.std() * np.sqrt(252)

    # Vol regime relative to historical
    vol_ratio = recent_vol / long_vol if long_vol > 0 else 1.0

    if vol_ratio > 1.5:
        regime = "high_volatility"
    elif vol_ratio < 0.7:
        regime = "low_volatility"
    else:
        regime = "normal_volatility"

    # Percentile of current vol vs history
    rolling_vol = returns.rolling(period).std() * np.sqrt(252)
    vol_percentile = float(
        (rolling_vol < recent_vol).sum() / len(rolling_vol) * 100
    ) if len(rolling_vol) > 0 else 50.0

    return {
        "realized_vol": float(recent_vol),
        "long_term_vol": float(long_vol),
        "vol_ratio": float(vol_ratio),
        "vol_regime": regime,
        "vol_percentile": vol_percentile,
    }


def compute_momentum(prices: pd.Series) -> dict:
    """Compute momentum signals at multiple horizons."""
    current = prices.iloc[-1]
    result = {}

    for horizon, label in [(5, "1w"), (21, "1m"), (63, "3m"), (126, "6m"), (252, "1y")]:
        if len(prices) > horizon:
            past = prices.iloc[-(horizon + 1)]
            result[f"return_{label}"] = float((current / past - 1) * 100)
        else:
            result[f"return_{label}"] = None

    return result


def analyze_instrument(prices: pd.Series, instrument: str) -> dict:
    """Run full technical analysis on a single instrument.

    Args:
        prices: Series of adjusted close prices (oldest first).
        instrument: Instrument name.

    Returns:
        Dict with all technical indicators.
    """
    if len(prices) < 30:
        logger.warning(f"Insufficient data for {instrument}: {len(prices)} rows")
        return {"instrument": instrument, "error": "insufficient_data"}

    return {
        "instrument": instrument,
        "current_price": float(prices.iloc[-1]),
        "rsi": compute_rsi(prices),
        "macd": compute_macd(prices),
        "bollinger": compute_bollinger_bands(prices),
        "trend": compute_trend(prices),
        "volatility": compute_volatility(prices),
        "momentum": compute_momentum(prices),
    }


def generate_signal(market_data: pd.DataFrame, as_of: datetime) -> Signal:
    """Generate a technical signal from market data.

    Args:
        market_data: DataFrame from DataStore.get_market_data_as_of()
        as_of: Current point-in-time.

    Returns:
        Signal with technical analysis for all instruments.
    """
    instruments = market_data["instrument"].unique()
    analysis = {}

    for instrument in instruments:
        inst_data = market_data[market_data["instrument"] == instrument].sort_values("date")
        prices = inst_data["adj_close"]

        if len(prices) < 30:
            continue

        analysis[instrument] = analyze_instrument(prices, instrument)

    # Compute overall market breadth
    bullish_count = sum(
        1 for a in analysis.values()
        if isinstance(a.get("trend"), dict) and "uptrend" in a["trend"].get("trend", "")
    )
    total = len(analysis)
    breadth = bullish_count / total if total > 0 else 0.5

    return Signal(
        agent_name="market_technician",
        signal_type="technical",
        as_of=as_of,
        confidence=0.8,  # Deterministic signals have fixed confidence
        payload={
            "instruments": analysis,
            "market_breadth": breadth,
            "breadth_label": "bullish" if breadth > 0.6 else "bearish" if breadth < 0.4 else "mixed",
        },
    )
