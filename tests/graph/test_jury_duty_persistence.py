"""Tests for jury duty (new juror) vote persistence.

All agents and DataStore are mocked — no real LLM calls or DB connections.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

AS_OF = datetime(2026, 3, 15, 12, 0, 0)

SPECIALIST_STATE = {
    "run_id": "test-run-001",
    "as_of": AS_OF,
    "signals": [],
    "current_portfolio": {},
    "council_round": 1,
    "strategist_vote": {"agent_name": "strategist"},
    "contrarian_vote": {"agent_name": "contrarian"},
}

SYNTHESIZER_STATE = {
    "run_id": "test-run-001",
    "as_of": AS_OF,
    "signals": [],
    "current_portfolio": {},
    "council_round": 1,
    "strategist_vote": {"agent_name": "strategist"},
    "contrarian_vote": {"agent_name": "contrarian"},
    "risk_manager_vote": {"agent_name": "risk_manager"},
    "quant_vote": {"agent_name": "quant"},
    "behavioral_skeptic_vote": {"agent_name": "behavioral_skeptic"},
}


def _make_fake_vote(agent_name: str, conviction: float = 0.65) -> MagicMock:
    vote = MagicMock()
    vote.agent_name = agent_name
    vote.overall_conviction = conviction
    vote.views = []
    vote.summary = f"{agent_name} summary."
    vote.model_used = "openai/gpt-4o"
    vote.model_dump.return_value = {
        "agent_name": agent_name,
        "overall_conviction": conviction,
        "views": [],
        "summary": f"{agent_name} summary.",
        "model_used": "openai/gpt-4o",
    }
    return vote


def test_risk_manager_node_calls_store_council_vote():
    from src.graph.nodes import make_risk_manager_node

    mock_store = MagicMock()
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = _make_fake_vote("risk_manager")

    with patch("src.graph.nodes._get_risk_manager", return_value=mock_agent):
        node = make_risk_manager_node(mock_store)
        node(SPECIALIST_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args
    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "risk_manager"
    assert vote_arg["as_of"] == AS_OF.isoformat()


def test_quant_node_calls_store_council_vote():
    from src.graph.nodes import make_quant_node

    mock_store = MagicMock()
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = _make_fake_vote("quant")

    with patch("src.graph.nodes._get_quant", return_value=mock_agent):
        node = make_quant_node(mock_store)
        node(SPECIALIST_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args
    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "quant"
    assert vote_arg["as_of"] == AS_OF.isoformat()


def test_behavioral_skeptic_node_calls_store_council_vote():
    from src.graph.nodes import make_behavioral_skeptic_node

    mock_store = MagicMock()
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = _make_fake_vote("behavioral_skeptic")

    with patch("src.graph.nodes._get_behavioral_skeptic", return_value=mock_agent):
        node = make_behavioral_skeptic_node(mock_store)
        node(SPECIALIST_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args
    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "behavioral_skeptic"
    assert vote_arg["as_of"] == AS_OF.isoformat()


def test_new_nodes_skip_persistence_when_store_is_none():
    from src.graph.nodes import make_risk_manager_node

    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = _make_fake_vote("risk_manager")

    with patch("src.graph.nodes._get_risk_manager", return_value=mock_agent):
        node = make_risk_manager_node(None)
        result = node(SPECIALIST_STATE)

    # If the 'if store is not None:' guard is absent, calling None.store_council_vote()
    # would raise AttributeError here, causing the test to fail.
    assert "risk_manager_vote" in result
