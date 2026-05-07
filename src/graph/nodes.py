"""LangGraph node functions.

Each node function takes the TradingState, performs its work, and returns
a partial state update. These are wired together in workflow.py.
"""

from __future__ import annotations

from datetime import datetime

from src.agents.council.behavioral_skeptic import BehavioralSkeptic
from src.agents.council.contrarian import Contrarian
from src.agents.council.quant import Quant
from src.agents.council.risk_manager import RiskManager
from src.agents.council.strategist import Strategist
from src.agents.council.synthesizer import Synthesizer
from src.agents.execution.order_manager import apply_orders_to_portfolio, generate_orders
from src.agents.execution.portfolio_constructor import construct_portfolio
from src.agents.gatherers.asset_mapper import AssetMapper
from src.agents.gatherers.macro_sentinel import MacroSentinel
from src.agents.gatherers.market_technician import generate_signal as tech_signal
from src.state.schema import Signal
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("graph.nodes")

# Lazy-initialized singletons (created on first use to avoid import-time API calls)
_macro_sentinel = None
_strategist = None
_contrarian = None
_synthesizer = None
_risk_manager = None
_quant = None
_behavioral_skeptic = None
_asset_mapper = None


def _get_macro_sentinel() -> MacroSentinel:
    global _macro_sentinel
    if _macro_sentinel is None:
        _macro_sentinel = MacroSentinel()
    return _macro_sentinel


def _get_strategist() -> Strategist:
    global _strategist
    if _strategist is None:
        _strategist = Strategist()
    return _strategist


def _get_contrarian() -> Contrarian:
    global _contrarian
    if _contrarian is None:
        _contrarian = Contrarian()
    return _contrarian


def _get_synthesizer() -> Synthesizer:
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = Synthesizer()
    return _synthesizer


def _get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


def _get_quant() -> Quant:
    global _quant
    if _quant is None:
        _quant = Quant()
    return _quant


def _get_behavioral_skeptic() -> BehavioralSkeptic:
    global _behavioral_skeptic
    if _behavioral_skeptic is None:
        _behavioral_skeptic = BehavioralSkeptic()
    return _behavioral_skeptic


def _get_asset_mapper() -> AssetMapper:
    global _asset_mapper
    if _asset_mapper is None:
        _asset_mapper = AssetMapper()
    return _asset_mapper


# ---------------------------------------------------------------------------
# Layer 1: Information Gathering Nodes
# ---------------------------------------------------------------------------


def macro_sentinel_node(state: dict) -> dict:
    """Macro Sentinel gathering node (GPT-4o)."""
    as_of = state["as_of"]
    store = DataStore()

    logger.info(f"[Macro Sentinel] Analyzing macro data as of {as_of}")
    agent = _get_macro_sentinel()
    signal = agent.generate_signal(store, as_of)

    return {"signals": [signal.model_dump()]}


def market_technician_node(state: dict) -> dict:
    """Market Technician gathering node (deterministic)."""
    as_of = state["as_of"]
    store = DataStore()

    logger.info(f"[Market Technician] Computing technical indicators as of {as_of}")
    market_data = store.get_market_data_as_of(as_of, lookback_days=252)

    if market_data.empty:
        logger.warning("[Market Technician] No market data available")
        return {"signals": []}

    signal = tech_signal(market_data, as_of)
    return {"signals": [signal.model_dump()]}


def narrative_analyst_node(state: dict) -> dict:
    """Narrative Analyst gathering node (Claude).

    Placeholder — full implementation in Phase 4.
    Returns empty signal if the agent module isn't ready.
    """
    as_of = state["as_of"]

    try:
        from src.agents.gatherers.narrative_analyst import NarrativeAnalyst
        store = DataStore()
        agent = NarrativeAnalyst()
        signal = agent.generate_signal(store, as_of)
        return {"signals": [signal.model_dump()]}
    except (ImportError, Exception) as e:
        logger.info(f"[Narrative Analyst] Not available: {e}")
        return {"signals": []}


def sentiment_scout_node(state: dict) -> dict:
    """Sentiment Scout gathering node (Gemini).

    Placeholder — full implementation in Phase 4.
    Returns empty signal if the agent module isn't ready.
    """
    as_of = state["as_of"]

    try:
        from src.agents.gatherers.sentiment_scout import SentimentScout
        store = DataStore()
        agent = SentimentScout()
        signal = agent.generate_signal(store, as_of)
        return {"signals": [signal.model_dump()]}
    except (ImportError, Exception) as e:
        logger.info(f"[Sentiment Scout] Not available: {e}")
        return {"signals": []}


# ---------------------------------------------------------------------------
# Signal Aggregator
# ---------------------------------------------------------------------------


def signal_aggregator_node(state: dict) -> dict:
    """Aggregates all gathered signals. No transformation — just a sync point."""
    signals = state.get("signals", [])
    logger.info(f"[Aggregator] Collected {len(signals)} signals")

    # Log which signal types we have
    types = [s.get("signal_type", "unknown") for s in signals]
    logger.info(f"[Aggregator] Signal types: {types}")

    return {}  # No state mutation — signals already accumulated via operator.add


def asset_mapper_node(state: dict) -> dict:
    """Asset Mapper node — translates signals to per-ticker directional views."""
    signals = state.get("signals", [])
    as_of = state["as_of"]

    if len(signals) < 2:
        logger.info("[Asset Mapper] Fewer than 2 signals — skipping LLM call")
        return {"signals": []}

    logger.info(f"[Asset Mapper] Mapping {len(signals)} signals to asset views")
    mapper = _get_asset_mapper()
    payload = mapper.map_assets(signals, as_of)

    signal = Signal(
        agent_name="asset_mapper",
        signal_type="asset_map",
        as_of=as_of,
        confidence=payload.get("confidence", 0.0),
        payload=payload,
    )
    return {"signals": [signal.model_dump()]}


# ---------------------------------------------------------------------------
# Layer 2: Council Debate Nodes
# ---------------------------------------------------------------------------


def make_strategist_node(store=None):
    """Factory that returns a Strategist node function.

    Args:
        store: DataStore instance for persisting votes, or None to skip persistence.
    """
    def strategist_node(state: dict) -> dict:
        as_of = state["as_of"]
        signals = state.get("signals", [])
        current_portfolio = state.get("current_portfolio", {})
        round_num = state.get("council_round", 0) + 1

        logger.info(f"[Strategist] Debate round {round_num}")
        data_store = DataStore()
        agent = _get_strategist()

        vote = agent.generate_vote(signals, current_portfolio, as_of, data_store)
        vote_data = vote.model_dump()

        logger.info(f"[Strategist] Conviction: {vote.overall_conviction:.2f}")
        logger.info(f"[Strategist] Thesis: {vote.summary[:100]}")

        if store is not None:
            try:
                store.store_council_vote(
                    run_id=state["run_id"],
                    vote={
                        "agent_name": vote_data["agent_name"],
                        "as_of": as_of.isoformat(),
                        "overall_conviction": vote_data["overall_conviction"],
                        "views": vote_data["views"],
                        "summary": vote_data["summary"],
                        "model_used": vote_data["model_used"],
                    },
                    round_number=round_num,
                )
            except Exception as e:
                logger.warning(f"Failed to persist council vote: {e}")

        return {
            "strategist_vote": vote_data,
            "council_round": round_num,
        }

    return strategist_node


def make_contrarian_node(store=None):
    """Factory that returns a Contrarian node function.

    Args:
        store: DataStore instance for persisting votes, or None to skip persistence.
    """
    def contrarian_node(state: dict) -> dict:
        as_of = state["as_of"]
        signals = state.get("signals", [])
        strategist_vote = state.get("strategist_vote", {})
        current_portfolio = state.get("current_portfolio", {})
        round_num = state.get("council_round", 1)

        logger.info("[Contrarian] Challenging the Strategist")
        data_store = DataStore()
        agent = _get_contrarian()

        vote = agent.generate_vote(signals, strategist_vote, current_portfolio, as_of, data_store)
        vote_data = vote.model_dump()

        logger.info(f"[Contrarian] Conviction: {vote.overall_conviction:.2f}")
        logger.info(f"[Contrarian] Counter-thesis: {vote.summary[:100]}")

        if store is not None:
            try:
                store.store_council_vote(
                    run_id=state["run_id"],
                    vote={
                        "agent_name": vote_data["agent_name"],
                        "as_of": as_of.isoformat(),
                        "overall_conviction": vote_data["overall_conviction"],
                        "views": vote_data["views"],
                        "summary": vote_data["summary"],
                        "model_used": vote_data["model_used"],
                    },
                    round_number=round_num,
                )
            except Exception as e:
                logger.warning(f"Failed to persist council vote: {e}")

        return {"contrarian_vote": vote_data}

    return contrarian_node


def make_risk_manager_node(store=None):
    """Factory that returns a Risk Manager node function."""
    def risk_manager_node(state: dict) -> dict:
        as_of = state["as_of"]
        signals = state.get("signals", [])
        strategist_vote = state.get("strategist_vote", {})
        contrarian_vote = state.get("contrarian_vote", {})
        current_portfolio = state.get("current_portfolio", {})
        round_num = state.get("council_round", 1)

        logger.info("[Risk Manager] Assessing tail risk")
        data_store = DataStore()
        agent = _get_risk_manager()
        vote = agent.generate_vote(
            signals, strategist_vote, contrarian_vote, current_portfolio, as_of, data_store
        )
        vote_data = vote.model_dump()

        logger.info(f"[Risk Manager] Conviction: {vote.overall_conviction:.2f}")

        if store is not None:
            try:
                store.store_council_vote(
                    run_id=state["run_id"],
                    vote={
                        "agent_name": vote_data["agent_name"],
                        "as_of": as_of.isoformat(),
                        "overall_conviction": vote_data["overall_conviction"],
                        "views": vote_data["views"],
                        "summary": vote_data["summary"],
                        "model_used": vote_data["model_used"],
                    },
                    round_number=round_num,
                )
            except Exception as e:
                logger.warning(f"Failed to persist risk_manager vote: {e}")

        return {"risk_manager_vote": vote_data}

    return risk_manager_node


def make_quant_node(store=None):
    """Factory that returns a Quant node function."""
    def quant_node(state: dict) -> dict:
        as_of = state["as_of"]
        signals = state.get("signals", [])
        strategist_vote = state.get("strategist_vote", {})
        contrarian_vote = state.get("contrarian_vote", {})
        current_portfolio = state.get("current_portfolio", {})
        round_num = state.get("council_round", 1)

        logger.info("[Quant] Computing systematic view")
        data_store = DataStore()
        agent = _get_quant()
        vote = agent.generate_vote(
            signals, strategist_vote, contrarian_vote, current_portfolio, as_of, data_store
        )
        vote_data = vote.model_dump()

        logger.info(f"[Quant] Conviction: {vote.overall_conviction:.2f}")

        if store is not None:
            try:
                store.store_council_vote(
                    run_id=state["run_id"],
                    vote={
                        "agent_name": vote_data["agent_name"],
                        "as_of": as_of.isoformat(),
                        "overall_conviction": vote_data["overall_conviction"],
                        "views": vote_data["views"],
                        "summary": vote_data["summary"],
                        "model_used": vote_data["model_used"],
                    },
                    round_number=round_num,
                )
            except Exception as e:
                logger.warning(f"Failed to persist quant vote: {e}")

        return {"quant_vote": vote_data}

    return quant_node


def make_behavioral_skeptic_node(store=None):
    """Factory that returns a Behavioral Skeptic node function."""
    def behavioral_skeptic_node(state: dict) -> dict:
        as_of = state["as_of"]
        signals = state.get("signals", [])
        strategist_vote = state.get("strategist_vote", {})
        contrarian_vote = state.get("contrarian_vote", {})
        current_portfolio = state.get("current_portfolio", {})
        round_num = state.get("council_round", 1)

        logger.info("[Behavioral Skeptic] Challenging crowd positioning")
        data_store = DataStore()
        agent = _get_behavioral_skeptic()
        vote = agent.generate_vote(
            signals, strategist_vote, contrarian_vote, current_portfolio, as_of, data_store
        )
        vote_data = vote.model_dump()

        logger.info(f"[Behavioral Skeptic] Conviction: {vote.overall_conviction:.2f}")

        if store is not None:
            try:
                store.store_council_vote(
                    run_id=state["run_id"],
                    vote={
                        "agent_name": vote_data["agent_name"],
                        "as_of": as_of.isoformat(),
                        "overall_conviction": vote_data["overall_conviction"],
                        "views": vote_data["views"],
                        "summary": vote_data["summary"],
                        "model_used": vote_data["model_used"],
                    },
                    round_number=round_num,
                )
            except Exception as e:
                logger.warning(f"Failed to persist behavioral_skeptic vote: {e}")

        return {"behavioral_skeptic_vote": vote_data}

    return behavioral_skeptic_node


def make_synthesizer_node(store=None):
    """Factory that returns a Synthesizer node function.

    Args:
        store: DataStore instance for persisting votes, or None to skip persistence.
    """
    def synthesizer_node(state: dict) -> dict:
        as_of = state["as_of"]
        strategist_vote = state.get("strategist_vote", {})
        contrarian_vote = state.get("contrarian_vote", {})
        current_portfolio = state.get("current_portfolio", {})
        round_num = state.get("council_round", 1)

        logger.info(f"[Synthesizer] Mediating round {round_num}")
        agent = _get_synthesizer()

        vote = agent.generate_vote(
            strategist_vote,
            contrarian_vote,
            state.get("risk_manager_vote", {}),
            state.get("quant_vote", {}),
            state.get("behavioral_skeptic_vote", {}),
            current_portfolio,
            as_of,
            round_num,
        )
        vote_data = vote.model_dump()

        logger.info(f"[Synthesizer] Final conviction: {vote.overall_conviction:.2f}")
        logger.info(f"[Synthesizer] Decision: {vote.summary[:100]}")

        if store is not None:
            try:
                store.store_council_vote(
                    run_id=state["run_id"],
                    vote={
                        "agent_name": vote_data["agent_name"],
                        "as_of": as_of.isoformat(),
                        "overall_conviction": vote_data["overall_conviction"],
                        "views": vote_data["views"],
                        "summary": vote_data["summary"],
                        "model_used": vote_data["model_used"],
                    },
                    round_number=round_num,
                )
            except Exception as e:
                logger.warning(f"Failed to persist council vote: {e}")

        return {"synthesizer_decision": vote_data}

    return synthesizer_node


# ---------------------------------------------------------------------------
# Layer 3: Execution Nodes
# ---------------------------------------------------------------------------


def portfolio_constructor_node(state: dict) -> dict:
    """Portfolio Constructor (deterministic)."""
    synthesizer_decision = state.get("synthesizer_decision", {})
    current_portfolio = state.get("current_portfolio", {})

    logger.info("[Portfolio Constructor] Building target portfolio")
    target_weights = construct_portfolio(synthesizer_decision, current_portfolio)

    return {"target_weights": target_weights}


def order_manager_node(state: dict) -> dict:
    """Order Manager (deterministic)."""
    current_weights = state.get("current_portfolio", {})
    target_weights = state.get("target_weights", {})
    nav = state.get("nav", 1_000_000)

    logger.info("[Order Manager] Generating trade orders")
    orders = generate_orders(current_weights, target_weights, nav)

    return {"trade_orders": orders}
