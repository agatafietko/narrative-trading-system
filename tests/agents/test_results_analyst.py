"""Tests for ResultsAnalyst agent."""
from unittest.mock import patch
from src.agents.analysis.results_analyst import ResultsAnalyst


def test_explain_returns_string():
    agent = ResultsAnalyst()
    with patch.object(agent, "_call_claude", return_value="Test explanation"):
        result = agent.explain("jury_duty", {"votes": []})
    assert isinstance(result, str)
    assert len(result) > 0


def test_explain_full_run_returns_string():
    agent = ResultsAnalyst()
    with patch.object(agent, "_call_claude", return_value="Full report text"):
        result = agent.explain("full_run", {"votes": [], "metrics": {}, "ablation": {}})
    assert isinstance(result, str)


def test_explain_invalid_mode_raises():
    agent = ResultsAnalyst()
    try:
        agent.explain("bad_mode", {})
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_call_claude_failure_returns_error_string():
    agent = ResultsAnalyst()
    with patch.object(agent, "_call_claude", side_effect=Exception("API error")):
        result = agent.explain("jury_duty", {"votes": []})
    assert "unavailable" in result.lower()


def test_jury_duty_data_shape():
    """ResultsAnalyst.explain accepts the data shape that page_jury() will pass."""
    agent = ResultsAnalyst()
    jury_data = {
        "selected_date": "2026-05-01",
        "avg_conviction": 0.58,
        "consensus_reached": False,
        "votes": [
            {
                "agent_name": "strategist",
                "overall_conviction": 0.70,
                "summary": "Bearish on equities.",
                "model_used": "openai/gpt-4o",
            }
        ],
    }
    with patch.object(agent, "_call_claude", return_value="Explanation here"):
        result = agent.explain("jury_duty", jury_data)
    assert isinstance(result, str)
