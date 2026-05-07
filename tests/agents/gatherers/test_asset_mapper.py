"""Tests for AssetMapper gatherer agent."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.agents.gatherers.asset_mapper import AssetMapper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AS_OF = datetime(2026, 5, 7, 9, 0, 0)

SAMPLE_SIGNALS = [
    {
        "agent_name": "macro_sentinel",
        "signal_type": "macro",
        "as_of": AS_OF.isoformat(),
        "confidence": 0.8,
        "payload": {
            "regime": "stagflation",
            "regime_confidence": 0.8,
            "macro_summary": "High inflation, slowing growth, tight Fed.",
        },
    },
    {
        "agent_name": "market_technician",
        "signal_type": "technical",
        "as_of": AS_OF.isoformat(),
        "confidence": 0.7,
        "payload": {
            "momentum_summary": "Equities oversold, bonds recovering.",
            "indicators": {
                "SPY": {"rsi": 32.1},
                "QQQ": {"rsi": 29.5},
                "TLT": {"rsi": 55.0},
                "GLD": {"rsi": 61.2},
            },
        },
    },
    {
        "agent_name": "narrative_analyst",
        "signal_type": "narrative",
        "as_of": AS_OF.isoformat(),
        "confidence": 0.75,
        "payload": {
            "dominant_narratives": ["tariff uncertainty", "Fed pause"],
            "overall_news_sentiment": "bearish",
        },
    },
]

VALID_LLM_RESPONSE = """{
    "views": {
        "SPY": -0.6,
        "QQQ": -0.7,
        "IWM": -0.5,
        "EEM": -0.4,
        "TLT": 0.5,
        "SHY": 0.3,
        "GLD": 0.8,
        "USO": 0.1,
        "UUP": 0.2,
        "VIXY": 0.6,
        "BTC-USD": -0.3
    },
    "rationale": {
        "SPY": "Stagflation regime historically negative for large-cap equities.",
        "GLD": "Gold benefits from inflation uncertainty and dollar weakness."
    },
    "dominant_theme": "flight-to-quality amid tariff uncertainty",
    "confidence": 0.75
}"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_map_assets_returns_all_tickers():
    """All 11 tickers must be present in views even if LLM omits some."""
    agent = AssetMapper()
    mock_response = {"content": VALID_LLM_RESPONSE, "model_used": "anthropic/claude-sonnet-4-20250514",
                     "prompt_hash": "abc", "response_hash": "def", "latency_ms": 800}
    with patch.object(agent, "call_llm", return_value=mock_response):
        result = agent.map_assets(SAMPLE_SIGNALS, AS_OF)

    assert set(result["views"].keys()) == set(AssetMapper.INSTRUMENTS)


def test_map_assets_scores_in_range():
    """All scores must be clamped to [-1.0, 1.0]."""
    # LLM returns out-of-range scores
    bad_scores = """{
        "views": {"SPY": 2.5, "QQQ": -3.0, "IWM": 0.5, "EEM": 0.0,
                  "TLT": 0.0, "SHY": 0.0, "GLD": 0.0, "USO": 0.0,
                  "UUP": 0.0, "VIXY": 0.0, "BTC-USD": 0.0},
        "rationale": {}, "dominant_theme": "", "confidence": 0.5
    }"""
    agent = AssetMapper()
    mock_response = {"content": bad_scores, "model_used": "anthropic/claude-sonnet-4-20250514",
                     "prompt_hash": "abc", "response_hash": "def", "latency_ms": 500}
    with patch.object(agent, "call_llm", return_value=mock_response):
        result = agent.map_assets(SAMPLE_SIGNALS, AS_OF)

    for ticker, score in result["views"].items():
        assert -1.0 <= score <= 1.0, f"{ticker} score {score} out of range"


def test_map_assets_graceful_on_bad_json():
    """Malformed LLM response returns views={} with confidence=0."""
    agent = AssetMapper()
    mock_response = {"content": "This is not JSON at all!!!", "model_used": "anthropic/claude-sonnet-4-20250514",
                     "prompt_hash": "abc", "response_hash": "def", "latency_ms": 400}
    with patch.object(agent, "call_llm", return_value=mock_response):
        result = agent.map_assets(SAMPLE_SIGNALS, AS_OF)

    assert result["views"] == {}
    assert result["confidence"] == 0.0


def test_asset_mapper_node_skips_with_few_signals():
    """Node returns empty signal list when fewer than 2 signals are present."""
    from src.graph.nodes import asset_mapper_node

    state = {"signals": [SAMPLE_SIGNALS[0]], "as_of": AS_OF}
    result = asset_mapper_node(state)

    assert result == {"signals": []}


def test_asset_mapper_node_appends_signal():
    """Node returns one asset_map signal when given >=2 input signals."""
    from src.graph.nodes import asset_mapper_node
    from src.agents.gatherers.asset_mapper import AssetMapper

    mock_response = {"content": VALID_LLM_RESPONSE, "model_used": "anthropic/claude-sonnet-4-20250514",
                     "prompt_hash": "abc", "response_hash": "def", "latency_ms": 800}

    state = {"signals": SAMPLE_SIGNALS, "as_of": AS_OF}

    with patch.object(AssetMapper, "call_llm", return_value=mock_response):
        result = asset_mapper_node(state)

    assert len(result["signals"]) == 1
    sig = result["signals"][0]
    assert sig["signal_type"] == "asset_map"
    assert sig["agent_name"] == "asset_mapper"
    assert "views" in sig["payload"]
