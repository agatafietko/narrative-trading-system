"""Quant — pure signal-driven council member.

Uses GPT-4o-mini. Ignores narrative entirely. Trades only on
technical signals, momentum, and mean-reversion.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.agents.base import BaseAgent
from src.state.schema import CouncilVote, InstrumentView
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("agent.quant")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "quant.txt"
UNIVERSE_INSTRUMENTS = [
    "SP500", "NASDAQ100", "RUSSELL2000", "US_10Y", "US_2Y",
    "GOLD", "OIL_WTI", "DXY", "VIX", "MSCI_EM", "BITCOIN",
]


class Quant(BaseAgent):
    """Pure signal-driven, systematic council member."""

    def __init__(self):
        super().__init__("quant", "council.quant")
        self.prompt_template = PROMPT_PATH.read_text()

    def generate_vote(
        self,
        signals: list[dict],
        strategist_vote: dict,
        contrarian_vote: dict,
        current_portfolio: dict[str, float],
        as_of: datetime,
        store: DataStore | None = None,
    ) -> CouncilVote:
        signal_map = self._organize_signals(signals)

        feedback_section = ""
        if store:
            feedback = store.get_recent_feedback("quant", last_n=5)
            if feedback:
                feedback_section = "## Recent Performance Feedback\n"
                for fb in feedback[-3:]:
                    feedback_section += f"- Period {fb['period_end']}: score={fb['score']:.2f}"
                    if fb["note"]:
                        feedback_section += f" — {fb['note']}"
                    feedback_section += "\n"

        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            current_portfolio=json.dumps(current_portfolio, indent=2),
            strategist_vote=json.dumps(strategist_vote, indent=2, default=str),
            contrarian_vote=json.dumps(contrarian_vote, indent=2, default=str),
            macro_signal=json.dumps(signal_map.get("macro", {}), indent=2),
            technical_signal=json.dumps(signal_map.get("technical", {}), indent=2, default=str),
            narrative_signal=json.dumps(signal_map.get("narrative", {}), indent=2),
            sentiment_signal=json.dumps(signal_map.get("sentiment", {}), indent=2),
            feedback_section=feedback_section,
        )

        response = self.call_llm(prompt)
        parsed = self.parse_json_response(response["content"])

        views = []
        for view_data in parsed.get("views", []):
            views.append(InstrumentView(
                instrument=view_data.get("instrument", ""),
                direction=view_data.get("direction", "neutral"),
                conviction=view_data.get("conviction", 0.5),
                target_weight=view_data.get("target_weight", 0.0),
                reasoning=view_data.get("reasoning", ""),
            ))

        viewed_instruments = {v.instrument for v in views}
        for inst in UNIVERSE_INSTRUMENTS:
            if inst not in viewed_instruments:
                views.append(InstrumentView(
                    instrument=inst,
                    direction="neutral",
                    conviction=0.3,
                    target_weight=0.0,
                    reasoning="No signal",
                ))

        return CouncilVote(
            agent_name="quant",
            model_used=response["model_used"],
            overall_conviction=parsed.get("overall_conviction", 0.5),
            views=views,
            summary=parsed.get("quant_thesis", ""),
        )

    def _organize_signals(self, signals: list[dict]) -> dict[str, dict]:
        signal_map = {}
        for s in signals:
            signal_type = s.get("signal_type", "unknown")
            signal_map[signal_type] = s.get("payload", {})
        return signal_map
