"""LangGraph workflow definition.

Defines the StateGraph that wires all agents together:
  START -> [gatherers in parallel] -> aggregator -> council debate -> execution -> END

The graph supports two modes:
  - Full mode: All 4 gatherers + 3 council members + execution
  - Minimal mode: Macro Sentinel + Market Technician + Strategist only (single-agent baseline)
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.graph.nodes import (
    macro_sentinel_node,
    make_contrarian_node,
    make_strategist_node,
    make_synthesizer_node,
    market_technician_node,
    narrative_analyst_node,
    order_manager_node,
    portfolio_constructor_node,
    sentiment_scout_node,
    signal_aggregator_node,
)
from src.graph.routing import check_consensus
from src.state.schema import TradingState
from src.utils.logging import get_logger

logger = get_logger("graph.workflow")


def build_full_graph(store=None) -> StateGraph:
    """Build the full multi-agent workflow graph.

    Args:
        store: Optional DataStore instance. When provided, council nodes persist
               their votes to Supabase after each deliberation round.

    Graph structure:
        START
          |
          +---> macro_sentinel --------+
          +---> market_technician -----+---> signal_aggregator
          +---> narrative_analyst -----+          |
          +---> sentiment_scout -------+          v
                                             strategist
                                                 |
                                                 v
                                             contrarian
                                                 |
                                                 v
                                             synthesizer
                                              /       \\
                                    (low conv.)  (consensus)
                                        |            |
                                        v            v
                                   strategist  portfolio_constructor
                                   (loop)           |
                                                    v
                                              order_manager
                                                    |
                                                   END
    """
    builder = StateGraph(TradingState)

    # Layer 1: Information gathering nodes
    builder.add_node("macro_sentinel", macro_sentinel_node)
    builder.add_node("market_technician", market_technician_node)
    builder.add_node("narrative_analyst", narrative_analyst_node)
    builder.add_node("sentiment_scout", sentiment_scout_node)

    # Aggregator (sync point)
    builder.add_node("signal_aggregator", signal_aggregator_node)

    # Layer 2: Council debate nodes
    builder.add_node("strategist", make_strategist_node(store))
    builder.add_node("contrarian", make_contrarian_node(store))
    builder.add_node("synthesizer", make_synthesizer_node(store))

    # Layer 3: Execution nodes
    builder.add_node("portfolio_constructor", portfolio_constructor_node)
    builder.add_node("order_manager", order_manager_node)

    # Edges: START -> all gatherers (parallel fan-out)
    builder.add_edge(START, "macro_sentinel")
    builder.add_edge(START, "market_technician")
    builder.add_edge(START, "narrative_analyst")
    builder.add_edge(START, "sentiment_scout")

    # Edges: gatherers -> aggregator (fan-in)
    builder.add_edge("macro_sentinel", "signal_aggregator")
    builder.add_edge("market_technician", "signal_aggregator")
    builder.add_edge("narrative_analyst", "signal_aggregator")
    builder.add_edge("sentiment_scout", "signal_aggregator")

    # Edges: aggregator -> council debate (sequential)
    builder.add_edge("signal_aggregator", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "synthesizer")

    # Conditional edge: synthesizer -> consensus check
    builder.add_conditional_edges(
        "synthesizer",
        check_consensus,
        {
            "portfolio_constructor": "portfolio_constructor",
            "strategist": "strategist",  # Loop back for another round
        },
    )

    # Edges: execution pipeline
    builder.add_edge("portfolio_constructor", "order_manager")
    builder.add_edge("order_manager", END)

    return builder.compile()


def build_minimal_graph() -> StateGraph:
    """Build a minimal graph for the single-agent baseline.

    Only uses Macro Sentinel + Market Technician -> Strategist (no debate).
    Used for ablation: measuring the value of the full council.
    """
    builder = StateGraph(TradingState)

    # Only 2 gatherers
    builder.add_node("macro_sentinel", macro_sentinel_node)
    builder.add_node("market_technician", market_technician_node)
    builder.add_node("signal_aggregator", signal_aggregator_node)

    # Single council member (Strategist acts alone)
    builder.add_node("strategist", make_strategist_node(None))

    # Execution (Strategist output goes directly to portfolio constructor)
    builder.add_node("portfolio_constructor", _single_agent_constructor_node)
    builder.add_node("order_manager", order_manager_node)

    # Wiring
    builder.add_edge(START, "macro_sentinel")
    builder.add_edge(START, "market_technician")
    builder.add_edge("macro_sentinel", "signal_aggregator")
    builder.add_edge("market_technician", "signal_aggregator")
    builder.add_edge("signal_aggregator", "strategist")
    builder.add_edge("strategist", "portfolio_constructor")
    builder.add_edge("portfolio_constructor", "order_manager")
    builder.add_edge("order_manager", END)

    return builder.compile()


def build_no_narrative_graph() -> StateGraph:
    """Build graph without narrative/sentiment agents (ablation).

    Uses Macro Sentinel + Market Technician -> full council debate.
    Measures: does narrative data add value?
    """
    builder = StateGraph(TradingState)

    builder.add_node("macro_sentinel", macro_sentinel_node)
    builder.add_node("market_technician", market_technician_node)
    builder.add_node("signal_aggregator", signal_aggregator_node)
    builder.add_node("strategist", make_strategist_node(None))
    builder.add_node("contrarian", make_contrarian_node(None))
    builder.add_node("synthesizer", make_synthesizer_node(None))
    builder.add_node("portfolio_constructor", portfolio_constructor_node)
    builder.add_node("order_manager", order_manager_node)

    builder.add_edge(START, "macro_sentinel")
    builder.add_edge(START, "market_technician")
    builder.add_edge("macro_sentinel", "signal_aggregator")
    builder.add_edge("market_technician", "signal_aggregator")
    builder.add_edge("signal_aggregator", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "synthesizer")
    builder.add_conditional_edges(
        "synthesizer",
        check_consensus,
        {
            "portfolio_constructor": "portfolio_constructor",
            "strategist": "strategist",
        },
    )
    builder.add_edge("portfolio_constructor", "order_manager")
    builder.add_edge("order_manager", END)

    return builder.compile()


def _single_agent_constructor_node(state: dict) -> dict:
    """Adapt Strategist output for direct portfolio construction (no Synthesizer)."""
    from src.agents.execution.portfolio_constructor import construct_portfolio

    strategist_vote = state.get("strategist_vote", {})
    current_portfolio = state.get("current_portfolio", {})

    # Use Strategist vote as if it were the Synthesizer's decision
    target_weights = construct_portfolio(strategist_vote, current_portfolio)
    return {"target_weights": target_weights}


# ---------------------------------------------------------------------------
# Graph registry for easy selection
# ---------------------------------------------------------------------------

# "full" is intentionally absent — it requires a store parameter and is handled
# explicitly in get_graph. The registry contains only parameter-free builders.
GRAPH_REGISTRY = {
    "minimal": build_minimal_graph,
    "no_narrative": build_no_narrative_graph,
}


def get_graph(variant: str = "full", store=None):
    """Get a compiled graph by variant name.

    Args:
        variant: One of "full", "minimal", "no_narrative".
        store: Optional DataStore for council vote persistence (full graph only).
    """
    if variant == "full":
        return build_full_graph(store=store)
    if variant not in GRAPH_REGISTRY:
        raise ValueError(f"Unknown graph variant: {variant}. Options: {list(GRAPH_REGISTRY.keys())}")
    return GRAPH_REGISTRY[variant]()
