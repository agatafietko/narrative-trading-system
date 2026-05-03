"""Core state schema for the trading system.

Defines all TypedDicts used in the LangGraph state, plus Pydantic models
for structured agent outputs.
"""

from __future__ import annotations

import operator
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict


# ---------------------------------------------------------------------------
# Pydantic models for structured agent outputs
# ---------------------------------------------------------------------------


class Signal(BaseModel):
    """Output from an information-gathering agent."""

    agent_name: str
    signal_type: str  # "macro" | "technical" | "narrative" | "sentiment"
    as_of: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)


class InstrumentView(BaseModel):
    """A council member's view on a single instrument."""

    instrument: str
    direction: str  # "bullish" | "bearish" | "neutral"
    conviction: float = Field(ge=0.0, le=1.0)
    target_weight: float = Field(ge=-0.25, le=0.25)
    reasoning: str = ""


class CouncilVote(BaseModel):
    """Output from a council agent."""

    agent_name: str
    model_used: str
    overall_conviction: float = Field(ge=0.0, le=1.0)
    views: list[InstrumentView] = Field(default_factory=list)
    summary: str = ""

    def target_weights(self) -> dict[str, float]:
        """Extract instrument -> target_weight mapping."""
        return {v.instrument: v.target_weight for v in self.views}


class TradeOrder(BaseModel):
    """A single trade order."""

    instrument: str
    direction: str  # "buy" | "sell"
    weight_delta: float
    dollar_amount: float
    cost: float


class PerformanceReport(BaseModel):
    """Output from the backtest evaluator."""

    period_start: date
    period_end: date
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_costs: float
    agent_scores: dict[str, float] = Field(default_factory=dict)
    feedback_notes: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------


class TradingState(TypedDict):
    """The shared state passed through the LangGraph workflow."""

    # Metadata
    run_id: str
    as_of: datetime
    current_portfolio: dict[str, float]  # instrument -> weight
    nav: float  # Net asset value

    # Layer 1: Gathered signals (accumulated via operator.add)
    signals: Annotated[list[dict], operator.add]

    # Layer 2: Council deliberation
    strategist_vote: NotRequired[dict]
    contrarian_vote: NotRequired[dict]
    synthesizer_decision: NotRequired[dict]
    council_round: int

    # Layer 3: Execution
    target_weights: NotRequired[dict[str, float]]
    trade_orders: NotRequired[list[dict]]

    # Layer 4: Feedback
    performance_report: NotRequired[dict]
    agent_scores: NotRequired[dict[str, float]]
