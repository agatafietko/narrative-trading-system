"""Results Analyst — plain-English explainer for dashboard outputs.

Called directly from app.py on button click. Not part of the LangGraph graph.
Uses Claude Sonnet hardcoded (not swappable in ablations).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger("agent.results_analyst")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "results_analyst.txt"

INSTRUCTIONS = {
    "jury_duty": (
        "Explain this jury verdict in 3-5 plain-English sentences. "
        "Reference the actual conviction scores and agent names. "
        "Explain what the overall conviction level means for execution "
        "and why any jurors scored unusually high or low."
    ),
    "performance": (
        "Explain this portfolio performance in 3-5 plain-English sentences. "
        "Reference the actual return, Sharpe ratio, and max drawdown numbers. "
        "Put the numbers in context — is a Sharpe of 0.5 good or bad? "
        "What does the max drawdown tell us about risk?"
    ),
    "ablation": (
        "Explain these ablation results in 3-5 plain-English sentences. "
        "Compare the full system against the baselines. "
        "Explain what the ablation matrix is measuring and what the numbers "
        "reveal about which agents or data sources add the most value."
    ),
    "full_run": (
        "Write a structured analysis report with exactly these 4 sections, "
        "each 2-3 sentences:\n"
        "**Verdict:** What did the jury decide and did they reach consensus?\n"
        "**Portfolio Changes:** What was bought and sold and why?\n"
        "**Key Risks:** What did the Risk Manager and Behavioral Skeptic flag?\n"
        "**Watch List:** What should be monitored before the next rebalance?"
    ),
}

VALID_MODES = set(INSTRUCTIONS.keys())


class ResultsAnalyst:
    """On-demand plain-English explainer for dashboard results."""

    def __init__(self):
        self.prompt_template = PROMPT_PATH.read_text()
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        from langchain_anthropic import ChatAnthropic
        self._client = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            temperature=0,
            max_tokens=1000,
        )
        return self._client

    def _call_claude(self, prompt: str) -> str:
        client = self._get_client()
        response = client.invoke([("human", prompt)])
        return response.content if hasattr(response, "content") else str(response)

    def explain(self, mode: str, data: dict) -> str:
        """Generate a plain-English explanation for a dashboard section.

        Args:
            mode: One of 'jury_duty', 'performance', 'ablation', 'full_run'.
            data: Dict of data relevant to the section (votes, metrics, etc.).

        Returns:
            Plain-English explanation string.

        Raises:
            ValueError: If mode is not one of the valid modes.
        """
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode {mode!r}. Must be one of {sorted(VALID_MODES)}")

        prompt = self.prompt_template.format(
            mode=mode,
            data=json.dumps(data, indent=2, default=str),
            instructions=INSTRUCTIONS[mode],
        )

        try:
            result = self._call_claude(prompt)
            logger.info(f"ResultsAnalyst explained {mode}: {len(result)} chars")
            return result
        except Exception as e:
            logger.error(f"ResultsAnalyst failed for mode {mode}: {e}")
            return "Analysis unavailable — check your ANTHROPIC_API_KEY and try again."
