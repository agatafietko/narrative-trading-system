"""Macro Sentinel — macroeconomic analysis agent.

Uses GPT-4o to analyze FRED economic data and identify the current
macro regime, rate trajectory, and asset class implications.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from src.agents.base import BaseAgent
from src.state.schema import Signal
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("agent.macro_sentinel")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "macro_sentinel.txt"


class MacroSentinel(BaseAgent):
    """Analyzes macroeconomic indicators to identify regime and outlook."""

    def __init__(self):
        super().__init__("macro_sentinel", "gatherers.macro_sentinel")
        self.prompt_template = PROMPT_PATH.read_text()

    def generate_signal(self, store: DataStore, as_of: datetime) -> Signal:
        """Generate a macro signal from FRED and market data.

        Args:
            store: DataStore for point-in-time data access.
            as_of: Current simulation timestamp.

        Returns:
            Signal with macro analysis payload.
        """
        # Gather data (all filtered by known_at <= as_of)
        fred_data = store.get_fred_data_as_of(as_of)
        yield_data = self._format_yield_data(fred_data)
        dxy_data = self._format_dxy_data(store, as_of)
        fred_summary = self._format_fred_summary(fred_data)

        # Build prompt
        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            fred_data=fred_summary,
            yield_data=yield_data,
            dxy_data=dxy_data,
        )

        # Call LLM
        response = self.call_llm(prompt)
        payload = self.parse_json_response(response["content"])

        if not payload:
            logger.warning("Failed to parse macro signal, using defaults")
            payload = {
                "regime": "unknown",
                "regime_confidence": 0.3,
                "macro_summary": "Unable to analyze macro data",
            }

        return Signal(
            agent_name="macro_sentinel",
            signal_type="macro",
            as_of=as_of,
            confidence=payload.get("regime_confidence", 0.5),
            payload={
                **payload,
                "model_used": response["model_used"],
                "prompt_hash": response["prompt_hash"],
                "response_hash": response["response_hash"],
                "latency_ms": response["latency_ms"],
            },
        )

    def _format_fred_summary(self, fred_data: pd.DataFrame) -> str:
        """Format FRED data into a readable summary for the prompt."""
        if fred_data.empty:
            return "No FRED data available."

        lines = []
        for series_id in fred_data["series_id"].unique():
            series = fred_data[fred_data["series_id"] == series_id].sort_values("date")
            if series.empty:
                continue

            latest = series.iloc[-1]
            prev = series.iloc[-2] if len(series) >= 2 else latest

            change = latest["value"] - prev["value"]
            lines.append(
                f"- {series_id}: {latest['value']:.2f} "
                f"(prev: {prev['value']:.2f}, change: {change:+.2f}) "
                f"as of {latest['date']}"
            )

        return "\n".join(lines) if lines else "No FRED data available."

    def _format_yield_data(self, fred_data: pd.DataFrame) -> str:
        """Format yield curve data."""
        lines = []

        for series_id in ["DGS10", "DGS2", "T10Y2Y"]:
            series = fred_data[fred_data["series_id"] == series_id]
            if series.empty:
                continue
            latest = series.sort_values("date").iloc[-1]
            lines.append(f"- {series_id}: {latest['value']:.2f}% as of {latest['date']}")

        return "\n".join(lines) if lines else "Yield data not available."

    def _format_dxy_data(self, store: DataStore, as_of: datetime) -> str:
        """Format DXY (dollar index) recent movement."""
        market_data = store.get_market_data_as_of(as_of, ticker="UUP", lookback_days=30)
        if market_data.empty:
            return "DXY data not available."

        latest = market_data.iloc[-1]
        oldest = market_data.iloc[0]
        change_pct = (latest["adj_close"] / oldest["adj_close"] - 1) * 100

        return (
            f"DXY proxy (UUP): {latest['adj_close']:.2f} "
            f"(30d change: {change_pct:+.1f}%)"
        )
