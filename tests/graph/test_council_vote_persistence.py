"""Tests for council vote persistence.

All agents and DataStore are mocked — no real LLM calls or DB connections.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

AS_OF = datetime(2026, 3, 15, 12, 0, 0)

STRATEGIST_STATE = {
    "run_id": "test-run-001",
    "as_of": AS_OF,
    "signals": [],
    "current_portfolio": {},
    "council_round": 0,
}

CONTRARIAN_STATE = {
    "run_id": "test-run-001",
    "as_of": AS_OF,
    "signals": [],
    "current_portfolio": {},
    "council_round": 1,
    "strategist_vote": {"agent_name": "strategist"},
}

SYNTHESIZER_STATE = {
    "run_id": "test-run-001",
    "as_of": AS_OF,
    "signals": [],
    "current_portfolio": {},
    "council_round": 1,
    "strategist_vote": {"agent_name": "strategist"},
    "contrarian_vote": {"agent_name": "contrarian"},
}


# ---------------------------------------------------------------------------
# Test 1: Strategist node calls store_council_vote with correct fields
# ---------------------------------------------------------------------------

def test_strategist_node_calls_store_council_vote():
    from src.graph.nodes import make_strategist_node

    # Create local FAKE_VOTE to avoid shared MagicMock state across tests
    fake_vote = MagicMock()
    fake_vote.agent_name = "strategist"
    fake_vote.overall_conviction = 0.75
    fake_vote.views = [{"instrument": "SPY", "direction": 1, "conviction": 0.8}]
    fake_vote.summary = "Bullish thesis."
    fake_vote.model_used = "openai/gpt-4o"
    fake_vote.model_dump.return_value = {
        "agent_name": "strategist",
        "overall_conviction": 0.75,
        "views": [{"instrument": "SPY", "direction": 1, "conviction": 0.8}],
        "summary": "Bullish thesis.",
        "model_used": "openai/gpt-4o",
    }

    mock_store = MagicMock()
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = fake_vote

    with patch("src.graph.nodes._get_strategist", return_value=mock_agent), \
         patch("src.graph.nodes.DataStore"):
        node = make_strategist_node(mock_store)
        node(STRATEGIST_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args

    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1  # incremented from 0
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "strategist"
    assert vote_arg["overall_conviction"] == 0.75
    assert vote_arg["summary"] == "Bullish thesis."
    assert vote_arg["model_used"] == "openai/gpt-4o"
    assert vote_arg["as_of"] == AS_OF.isoformat()


# ---------------------------------------------------------------------------
# Test 2: Contrarian node calls store_council_vote with correct fields
# ---------------------------------------------------------------------------

def test_contrarian_node_calls_store_council_vote():
    from src.graph.nodes import make_contrarian_node

    mock_store = MagicMock()
    contrarian_vote = MagicMock()
    contrarian_vote.agent_name = "contrarian"
    contrarian_vote.overall_conviction = 0.45
    contrarian_vote.views = []
    contrarian_vote.summary = "Counter-thesis."
    contrarian_vote.model_used = "anthropic/claude-3-5-sonnet"
    contrarian_vote.model_dump.return_value = {
        "agent_name": "contrarian",
        "overall_conviction": 0.45,
        "views": [],
        "summary": "Counter-thesis.",
        "model_used": "anthropic/claude-3-5-sonnet",
    }
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = contrarian_vote

    with patch("src.graph.nodes._get_contrarian", return_value=mock_agent), \
         patch("src.graph.nodes.DataStore"):
        node = make_contrarian_node(mock_store)
        node(CONTRARIAN_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args

    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "contrarian"
    assert vote_arg["overall_conviction"] == 0.45
    assert vote_arg["as_of"] == AS_OF.isoformat()


# ---------------------------------------------------------------------------
# Test 3: Synthesizer node calls store_council_vote with correct fields
# ---------------------------------------------------------------------------

def test_synthesizer_node_calls_store_council_vote():
    from src.graph.nodes import make_synthesizer_node

    mock_store = MagicMock()
    synth_vote = MagicMock()
    synth_vote.agent_name = "synthesizer"
    synth_vote.overall_conviction = 0.62
    synth_vote.views = []
    synth_vote.summary = "Balanced decision."
    synth_vote.model_used = "meta-llama/llama-3-70b-instruct"
    synth_vote.model_dump.return_value = {
        "agent_name": "synthesizer",
        "overall_conviction": 0.62,
        "views": [],
        "summary": "Balanced decision.",
        "model_used": "meta-llama/llama-3-70b-instruct",
    }
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = synth_vote

    with patch("src.graph.nodes._get_synthesizer", return_value=mock_agent):
        node = make_synthesizer_node(mock_store)
        node(SYNTHESIZER_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args

    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "synthesizer"
    assert vote_arg["overall_conviction"] == 0.62
    assert vote_arg["as_of"] == AS_OF.isoformat()


# ---------------------------------------------------------------------------
# Test 4: When store=None, store_council_vote is never called (backward compat)
# ---------------------------------------------------------------------------

def test_no_store_skips_persistence():
    from src.graph.nodes import make_strategist_node

    # Create local FAKE_VOTE to avoid shared MagicMock state across tests
    fake_vote = MagicMock()
    fake_vote.agent_name = "strategist"
    fake_vote.overall_conviction = 0.75
    fake_vote.views = [{"instrument": "SPY", "direction": 1, "conviction": 0.8}]
    fake_vote.summary = "Bullish thesis."
    fake_vote.model_used = "openai/gpt-4o"
    fake_vote.model_dump.return_value = {
        "agent_name": "strategist",
        "overall_conviction": 0.75,
        "views": [{"instrument": "SPY", "direction": 1, "conviction": 0.8}],
        "summary": "Bullish thesis.",
        "model_used": "openai/gpt-4o",
    }

    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = fake_vote

    with patch("src.graph.nodes._get_strategist", return_value=mock_agent), \
         patch("src.graph.nodes.DataStore"):
        node = make_strategist_node(None)
        result = node(STRATEGIST_STATE)

    # Verify the function completes and returns proper state
    assert "strategist_vote" in result
    assert result["council_round"] == 1
    # If the 'if store:' guard is absent, calling None.store_council_vote()
    # would raise AttributeError here, causing the test to fail.
