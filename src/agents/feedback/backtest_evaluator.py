"""Backtest Evaluator — performance attribution and feedback agent.

Uses GPT-4o to evaluate each agent's accuracy after each rebalance cycle.
Produces scores and feedback notes that are injected into future prompts
(dynamic prompt injection / soft feedback loop).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.agents.base import BaseAgent
from src.state.schema import PerformanceReport
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("agent.backtest_evaluator")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "evaluator.txt"


class BacktestEvaluator(BaseAgent):
    """Evaluates agent performance and produces feedback for prompt injection."""

    def __init__(self):
        super().__init__("backtest_evaluator", "feedback.backtest_evaluator")
        self.prompt_template = PROMPT_PATH.read_text()

    def evaluate(
        self,
        store: DataStore,
        run_id: str,
        period_start: datetime,
        period_end: datetime,
        council_votes: dict,
        actual_returns: dict[str, float],
        portfolio_performance: dict,
    ) -> PerformanceReport:
        """Evaluate agent performance for a completed period.

        Args:
            store: DataStore for storage.
            run_id: Current run identifier.
            period_start: Start of evaluation period.
            period_end: End of evaluation period.
            council_votes: Dict with 'strategist', 'contrarian', 'synthesizer' votes.
            actual_returns: instrument -> actual return over the period.
            portfolio_performance: Portfolio metrics for the period.

        Returns:
            PerformanceReport with scores and feedback.
        """
        prompt = self.prompt_template.format(
            period_start=period_start.strftime("%Y-%m-%d"),
            period_end=period_end.strftime("%Y-%m-%d"),
            strategist_vote=json.dumps(
                council_votes.get("strategist", {}), indent=2, default=str
            ),
            contrarian_vote=json.dumps(
                council_votes.get("contrarian", {}), indent=2, default=str
            ),
            synthesizer_decision=json.dumps(
                council_votes.get("synthesizer", {}), indent=2, default=str
            ),
            actual_outcomes=json.dumps(actual_returns, indent=2),
            portfolio_performance=json.dumps(portfolio_performance, indent=2),
        )

        response = self.call_llm(prompt)
        parsed = self.parse_json_response(response["content"])

        agent_scores = parsed.get("agent_scores", {})
        feedback_notes = parsed.get("feedback_notes", {})

        report = PerformanceReport(
            period_start=period_start.date(),
            period_end=period_end.date(),
            total_return=portfolio_performance.get("total_return", 0),
            sharpe_ratio=portfolio_performance.get("sharpe_ratio", 0),
            max_drawdown=portfolio_performance.get("max_drawdown", 0),
            total_costs=portfolio_performance.get("total_costs", 0),
            agent_scores=agent_scores,
            feedback_notes=feedback_notes,
        )

        # Store feedback
        store.store_feedback(run_id, {
            "period_start": period_start.strftime("%Y-%m-%d"),
            "period_end": period_end.strftime("%Y-%m-%d"),
            "total_return": report.total_return,
            "sharpe_ratio": report.sharpe_ratio,
            "max_drawdown": report.max_drawdown,
            "agent_scores": agent_scores,
            "feedback_notes": feedback_notes,
        })

        logger.info(f"Evaluation complete: best={parsed.get('best_performer')}, "
                     f"worst={parsed.get('worst_performer')}")

        return report
