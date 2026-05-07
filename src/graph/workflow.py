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
    asset_mapper_node,
    macro_sentinel_node,
    make_behavioral_skeptic_node,
    make_contrarian_node,
    make_quant_node,
    make_risk_manager_node,
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
                                             asset_mapper
                                                  |
                                                  v
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

    # Asset Mapper (translates signals to per-ticker views before council debate)
    builder.add_node("asset_mapper", asset_mapper_node)

    # Layer 2: Council debate nodes
    builder.add_node("strategist", make_strategist_node(store))
    builder.add_node("contrarian", make_contrarian_node(store))
    builder.add_node("synthesizer", make_synthesizer_node(store))
    builder.add_node("risk_manager", make_risk_manager_node(store))
    builder.add_node("quant", make_quant_node(store))
    builder.add_node("behavioral_skeptic", make_behavioral_skeptic_node(store))

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

    # Edges: aggregator -> asset mapper -> council debate (sequential)
    builder.add_edge("signal_aggregator", "asset_mapper")
    builder.add_edge("asset_mapper", "strategist")
    builder.add_edge("strategist", "contrarian")
    # Fan-out: contrarian -> 3 specialist jurors in parallel
    builder.add_edge("contrarian", "risk_manager")
    builder.add_edge("contrarian", "quant")
    builder.add_edge("contrarian", "behavioral_skeptic")
    # Fan-in: all 3 specialists must complete before Synthesizer runs
    builder.add_edge("risk_manager", "synthesizer")
    builder.add_edge("quant", "synthesizer")
    builder.add_edge("behavioral_skeptic", "synthesizer")

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


def build_no_narrative_graph(store=None) -> StateGraph:
    """Build graph without narrative/sentiment agents (ablation).

    Uses Macro Sentinel + Market Technician -> full council debate.
    Measures: does narrative data add value?

    Args:
        store: Optional DataStore for persisting council votes.
    """
    builder = StateGraph(TradingState)

    builder.add_node("macro_sentinel", macro_sentinel_node)
    builder.add_node("market_technician", market_technician_node)
    builder.add_node("signal_aggregator", signal_aggregator_node)
    builder.add_node("asset_mapper", asset_mapper_node)
    builder.add_node("strategist", make_strategist_node(store))
    builder.add_node("contrarian", make_contrarian_node(store))
    builder.add_node("synthesizer", make_synthesizer_node(store))
    builder.add_node("risk_manager", make_risk_manager_node(store))
    builder.add_node("quant", make_quant_node(store))
    builder.add_node("behavioral_skeptic", make_behavioral_skeptic_node(store))
    builder.add_node("portfolio_constructor", portfolio_constructor_node)
    builder.add_node("order_manager", order_manager_node)

    builder.add_edge(START, "macro_sentinel")
    builder.add_edge(START, "market_technician")
    builder.add_edge("macro_sentinel", "signal_aggregator")
    builder.add_edge("market_technician", "signal_aggregator")
    builder.add_edge("signal_aggregator", "asset_mapper")
    builder.add_edge("asset_mapper", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "risk_manager")
    builder.add_edge("contrarian", "quant")
    builder.add_edge("contrarian", "behavioral_skeptic")
    builder.add_edge("risk_manager", "synthesizer")
    builder.add_edge("quant", "synthesizer")
    builder.add_edge("behavioral_skeptic", "synthesizer")
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


def build_no_sentiment_graph(store=None) -> StateGraph:
    """Build graph without Sentiment Scout (ablation).

    Uses Macro Sentinel + Market Technician + Narrative Analyst -> full council.
    Measures: does sentiment data add value beyond narrative alone?
    """
    builder = StateGraph(TradingState)

    builder.add_node("macro_sentinel", macro_sentinel_node)
    builder.add_node("market_technician", market_technician_node)
    builder.add_node("narrative_analyst", narrative_analyst_node)
    builder.add_node("signal_aggregator", signal_aggregator_node)
    builder.add_node("asset_mapper", asset_mapper_node)
    builder.add_node("strategist", make_strategist_node(store))
    builder.add_node("contrarian", make_contrarian_node(store))
    builder.add_node("synthesizer", make_synthesizer_node(store))
    builder.add_node("risk_manager", make_risk_manager_node(store))
    builder.add_node("quant", make_quant_node(store))
    builder.add_node("behavioral_skeptic", make_behavioral_skeptic_node(store))
    builder.add_node("portfolio_constructor", portfolio_constructor_node)
    builder.add_node("order_manager", order_manager_node)

    builder.add_edge(START, "macro_sentinel")
    builder.add_edge(START, "market_technician")
    builder.add_edge(START, "narrative_analyst")
    builder.add_edge("macro_sentinel", "signal_aggregator")
    builder.add_edge("market_technician", "signal_aggregator")
    builder.add_edge("narrative_analyst", "signal_aggregator")
    builder.add_edge("signal_aggregator", "asset_mapper")
    builder.add_edge("asset_mapper", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "risk_manager")
    builder.add_edge("contrarian", "quant")
    builder.add_edge("contrarian", "behavioral_skeptic")
    builder.add_edge("risk_manager", "synthesizer")
    builder.add_edge("quant", "synthesizer")
    builder.add_edge("behavioral_skeptic", "synthesizer")
    builder.add_conditional_edges(
        "synthesizer",
        check_consensus,
        {"portfolio_constructor": "portfolio_constructor", "strategist": "strategist"},
    )
    builder.add_edge("portfolio_constructor", "order_manager")
    builder.add_edge("order_manager", END)

    return builder.compile()


def build_no_feedback_graph(store=None) -> StateGraph:
    """Build full graph with feedback loop disabled (ablation).

    All gatherers and council members active, but council nodes receive
    store=None so no historical feedback is injected into their prompts.
    Measures: does the feedback loop add value?
    """
    builder = StateGraph(TradingState)

    builder.add_node("macro_sentinel", macro_sentinel_node)
    builder.add_node("market_technician", market_technician_node)
    builder.add_node("narrative_analyst", narrative_analyst_node)
    builder.add_node("sentiment_scout", sentiment_scout_node)
    builder.add_node("signal_aggregator", signal_aggregator_node)
    builder.add_node("asset_mapper", asset_mapper_node)
    # Council nodes get store=None → no feedback injected into prompts
    builder.add_node("strategist", make_strategist_node(None))
    builder.add_node("contrarian", make_contrarian_node(None))
    builder.add_node("synthesizer", make_synthesizer_node(None))
    builder.add_node("risk_manager", make_risk_manager_node(None))
    builder.add_node("quant", make_quant_node(None))
    builder.add_node("behavioral_skeptic", make_behavioral_skeptic_node(None))
    builder.add_node("portfolio_constructor", portfolio_constructor_node)
    builder.add_node("order_manager", order_manager_node)

    builder.add_edge(START, "macro_sentinel")
    builder.add_edge(START, "market_technician")
    builder.add_edge(START, "narrative_analyst")
    builder.add_edge(START, "sentiment_scout")
    builder.add_edge("macro_sentinel", "signal_aggregator")
    builder.add_edge("market_technician", "signal_aggregator")
    builder.add_edge("narrative_analyst", "signal_aggregator")
    builder.add_edge("sentiment_scout", "signal_aggregator")
    builder.add_edge("signal_aggregator", "asset_mapper")
    builder.add_edge("asset_mapper", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "risk_manager")
    builder.add_edge("contrarian", "quant")
    builder.add_edge("contrarian", "behavioral_skeptic")
    builder.add_edge("risk_manager", "synthesizer")
    builder.add_edge("quant", "synthesizer")
    builder.add_edge("behavioral_skeptic", "synthesizer")
    builder.add_conditional_edges(
        "synthesizer",
        check_consensus,
        {"portfolio_constructor": "portfolio_constructor", "strategist": "strategist"},
    )
    builder.add_edge("portfolio_constructor", "order_manager")
    builder.add_edge("order_manager", END)

    return builder.compile()


def build_homogeneous_graph(store=None) -> StateGraph:
    """Build full graph with all LLM agents forced to GPT-4o (ablation).

    Temporarily patches the HOMOGENEOUS_MODEL env var so BaseAgent._get_client()
    routes every provider to GPT-4o.  Measures: does model diversity add value?
    """
    import os
    os.environ["HOMOGENEOUS_MODEL"] = "gpt-4o"

    # Re-import nodes so they pick up the env var on client init
    from src.graph.nodes import (
        macro_sentinel_node as _ms,
        market_technician_node as _mt,
        narrative_analyst_node as _na,
        sentiment_scout_node as _ss,
        signal_aggregator_node as _sa,
        asset_mapper_node as _am,
        make_strategist_node as _mkst,
        make_contrarian_node as _mkcn,
        make_synthesizer_node as _mksy,
        make_risk_manager_node as _mkrm,
        make_quant_node as _mkq,
        make_behavioral_skeptic_node as _mkbs,
        portfolio_constructor_node as _pc,
        order_manager_node as _om,
    )

    builder = StateGraph(TradingState)
    builder.add_node("macro_sentinel", _ms)
    builder.add_node("market_technician", _mt)
    builder.add_node("narrative_analyst", _na)
    builder.add_node("sentiment_scout", _ss)
    builder.add_node("signal_aggregator", _sa)
    builder.add_node("asset_mapper", _am)
    builder.add_node("strategist", _mkst(store))
    builder.add_node("contrarian", _mkcn(store))
    builder.add_node("synthesizer", _mksy(store))
    builder.add_node("risk_manager", _mkrm(store))
    builder.add_node("quant", _mkq(store))
    builder.add_node("behavioral_skeptic", _mkbs(store))
    builder.add_node("portfolio_constructor", _pc)
    builder.add_node("order_manager", _om)

    builder.add_edge(START, "macro_sentinel")
    builder.add_edge(START, "market_technician")
    builder.add_edge(START, "narrative_analyst")
    builder.add_edge(START, "sentiment_scout")
    builder.add_edge("macro_sentinel", "signal_aggregator")
    builder.add_edge("market_technician", "signal_aggregator")
    builder.add_edge("narrative_analyst", "signal_aggregator")
    builder.add_edge("sentiment_scout", "signal_aggregator")
    builder.add_edge("signal_aggregator", "asset_mapper")
    builder.add_edge("asset_mapper", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "risk_manager")
    builder.add_edge("contrarian", "quant")
    builder.add_edge("contrarian", "behavioral_skeptic")
    builder.add_edge("risk_manager", "synthesizer")
    builder.add_edge("quant", "synthesizer")
    builder.add_edge("behavioral_skeptic", "synthesizer")
    builder.add_conditional_edges(
        "synthesizer",
        check_consensus,
        {"portfolio_constructor": "portfolio_constructor", "strategist": "strategist"},
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

# "full" and "no_narrative" are intentionally absent — they require a store
# parameter and are handled explicitly in get_graph.
# The registry contains only parameter-free builders.
GRAPH_REGISTRY = {
    "minimal": build_minimal_graph,
}


def get_graph(variant: str = "full", store=None):
    """Get a compiled graph by variant name.

    Args:
        variant: One of "full", "minimal", "no_narrative".
        store: Optional DataStore for council vote persistence.
               Ignored for the "minimal" variant (single-agent, no debate).
    """
    if variant == "full":
        return build_full_graph(store=store)
    if variant == "no_narrative":
        return build_no_narrative_graph(store=store)
    if variant == "no_sentiment":
        return build_no_sentiment_graph(store=store)
    if variant == "no_feedback":
        return build_no_feedback_graph(store=store)
    if variant == "homogeneous":
        return build_homogeneous_graph(store=store)
    if variant not in GRAPH_REGISTRY:
        raise ValueError(
            f"Unknown graph variant: {variant!r}. "
            f"Options: {['full', 'no_narrative'] + list(GRAPH_REGISTRY.keys())}"
        )
    return GRAPH_REGISTRY[variant]()
