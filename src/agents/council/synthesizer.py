"""Synthesizer — mediator and final decision maker.

Uses Llama 3.1 70B (via Together AI). Reads both the Strategist's and
Contrarian's arguments and produces the final consensus with target weights.

Academically novel: demonstrates an open-source model can effectively
arbitrate between two frontier models (GPT-4o and Claude).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from src.agents.base import BaseAgent
from src.state.schema import CouncilVote, InstrumentView
from src.utils.logging import get_logger

logger = get_logger("agent.synthesizer")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "synthesizer.txt"
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "settings.yaml"
UNIVERSE_INSTRUMENTS = [
    "SP500", "NASDAQ100", "RUSSELL2000", "US_10Y", "US_2Y",
    "GOLD", "OIL_WTI", "DXY", "VIX", "MSCI_EM", "BITCOIN",
]


class Synthesizer(BaseAgent):
    """Final decision maker who mediates between Strategist and Contrarian."""

    def __init__(self):
        super().__init__("synthesizer", "council.synthesizer")
        self.prompt_template = PROMPT_PATH.read_text()

        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        self.max_rounds = config["council"]["max_debate_rounds"]

    def generate_vote(
        self,
        strategist_vote: dict,
        contrarian_vote: dict,
        current_portfolio: dict[str, float],
        as_of: datetime,
        round_number: int = 1,
    ) -> CouncilVote:
        """Synthesize the Strategist's and Contrarian's views into a final decision.

        Args:
            strategist_vote: The Strategist's CouncilVote as a dict.
            contrarian_vote: The Contrarian's CouncilVote as a dict.
            current_portfolio: Current portfolio weights.
            as_of: Current timestamp.
            round_number: Current debate round (1 or 2).

        Returns:
            CouncilVote with the final consensus.
        """
        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            current_portfolio=json.dumps(current_portfolio, indent=2),
            strategist_vote=json.dumps(strategist_vote, indent=2, default=str),
            contrarian_vote=json.dumps(contrarian_vote, indent=2, default=str),
            round_number=round_number,
            max_rounds=self.max_rounds,
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

        # Ensure coverage of all instruments
        viewed_instruments = {v.instrument for v in views}
        for inst in UNIVERSE_INSTRUMENTS:
            if inst not in viewed_instruments:
                views.append(InstrumentView(
                    instrument=inst,
                    direction="neutral",
                    conviction=0.3,
                    target_weight=0.0,
                    reasoning="No consensus view",
                ))

        # Validate weight sum
        total_positive = sum(v.target_weight for v in views if v.target_weight > 0)
        if total_positive > 0.95:
            scale = 0.95 / total_positive
            for v in views:
                if v.target_weight > 0:
                    v.target_weight = round(v.target_weight * scale, 4)

        return CouncilVote(
            agent_name="synthesizer",
            model_used=response["model_used"],
            overall_conviction=parsed.get("overall_conviction", 0.5),
            views=views,
            summary=parsed.get("synthesis", parsed.get("final_thesis", "")),
        )
