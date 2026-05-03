"""Streamlit dashboard for the Narrative Trading System.

Shows portfolio performance, agent debate logs, current holdings,
ablation comparisons, and system architecture.

Run locally: streamlit run app.py
Deploy: Push to GitHub, connect to Streamlit Cloud
"""

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.state.store import DataStore

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Narrative Trading System",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("Narrative Trading System")
st.sidebar.markdown("Multi-agent narrative-to-portfolio trading")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    ["Portfolio Performance", "Agent Council", "Trade History",
     "Ablation Results", "System Architecture"],
)

# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------

@st.cache_resource
def get_store():
    return DataStore()


@st.cache_data(ttl=300)
def load_run_ids():
    store = get_store()
    return store.get_all_run_ids()


@st.cache_data(ttl=300)
def load_portfolio_history(run_id: str):
    store = get_store()
    return store.get_portfolio_history(run_id)


@st.cache_data(ttl=300)
def load_council_votes(run_id: str):
    store = get_store()
    return store.get_council_votes_for_run(run_id)


@st.cache_data(ttl=300)
def load_trade_orders(run_id: str):
    store = get_store()
    return store.get_trade_orders_for_run(run_id)


@st.cache_data(ttl=300)
def load_ablation_results():
    ablation_path = Path("data/ablation_results.json")
    if ablation_path.exists():
        with open(ablation_path) as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------------------
# Run selector
# ---------------------------------------------------------------------------

def run_selector():
    run_ids = load_run_ids()
    if not run_ids:
        st.warning("No backtest runs found. Run a backtest first.")
        st.code("python scripts/run_backtest.py --strategy technical_momentum")
        return None
    selected = st.sidebar.selectbox("Select Run", run_ids)
    return selected


# ---------------------------------------------------------------------------
# Page: Portfolio Performance
# ---------------------------------------------------------------------------

def page_portfolio():
    st.header("Portfolio Performance")

    run_id = run_selector()
    if not run_id:
        return

    history = load_portfolio_history(run_id)
    if history.empty:
        st.info("No portfolio data for this run.")
        return

    # NAV chart
    st.subheader("Net Asset Value")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=history["as_of"], y=history["nav"],
        mode="lines", name="Portfolio NAV",
        line=dict(color="#2563eb", width=2),
    ))
    fig.add_hline(y=1_000_000, line_dash="dash", line_color="gray",
                  annotation_text="Initial Capital")
    fig.update_layout(
        yaxis_title="NAV ($)",
        xaxis_title="Date",
        template="plotly_white",
        height=400,
    )
    st.plotly_chart(fig, width="stretch")

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    if len(history) >= 2:
        total_ret = (history["nav"].iloc[-1] / history["nav"].iloc[0] - 1)
        returns = history["nav"].pct_change().dropna()
        sharpe = (returns.mean() / returns.std() * (252 ** 0.5)) if returns.std() > 0 else 0
        peak = history["nav"].cummax()
        max_dd = ((history["nav"] - peak) / peak).min()
        total_cost = history["total_cost_incurred"].iloc[-1]

        col1.metric("Total Return", f"{total_ret:.2%}")
        col2.metric("Sharpe Ratio", f"{sharpe:.2f}")
        col3.metric("Max Drawdown", f"{max_dd:.2%}")
        col4.metric("Total Costs", f"${total_cost:,.0f}")

    # Current holdings
    st.subheader("Current Holdings")
    if not history.empty:
        latest = history.iloc[-1]
        weights_raw = latest["weights"]
        weights = json.loads(weights_raw) if isinstance(weights_raw, str) else weights_raw

        if weights:
            # Add cash
            cash = latest.get("cash_weight", 1 - sum(abs(v) for v in weights.values()))
            display_weights = {**weights, "CASH": cash}

            # Filter out near-zero weights
            display_weights = {k: v for k, v in display_weights.items() if abs(v) >= 0.005}

            fig_pie = px.pie(
                values=[abs(v) for v in display_weights.values()],
                names=list(display_weights.keys()),
                title=f"Portfolio Allocation (as of {latest['as_of'].date()})",
                hole=0.4,
            )
            fig_pie.update_layout(height=400)
            st.plotly_chart(fig_pie, width="stretch")

            # Table
            wdf = pd.DataFrame([
                {"Instrument": k, "Weight": f"{v:.2%}", "Direction": "Long" if v > 0 else "Short" if v < 0 else "Flat"}
                for k, v in sorted(display_weights.items(), key=lambda x: -abs(x[1]))
            ])
            st.dataframe(wdf, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Page: Agent Council
# ---------------------------------------------------------------------------

def page_council():
    st.header("Agent Council Debates")

    run_id = run_selector()
    if not run_id:
        return

    votes = load_council_votes(run_id)
    if not votes:
        st.info("No council votes recorded for this run. Run the full multi-agent backtest to see debates.")
        st.code("python scripts/run_ablation.py --variants full")
        return

    # Group by date
    dates = sorted(set(v["as_of"] for v in votes))

    selected_date = st.selectbox("Select debate date", dates)
    date_votes = [v for v in votes if v["as_of"] == selected_date]

    for vote in date_votes:
        agent = vote["agent_name"]
        conviction = vote.get("overall_conviction", 0)
        model = vote.get("model_used", "unknown")

        icon = {"strategist": "🎯", "contrarian": "⚡", "synthesizer": "⚖️"}.get(agent, "🤖")

        with st.expander(f"{icon} {agent.title()} — Conviction: {conviction:.0%} — {model}", expanded=True):
            summary = vote.get("summary", "No summary")
            st.markdown(f"**Thesis:** {summary}")

            views_raw = vote.get("views", "[]")
            views = json.loads(views_raw) if isinstance(views_raw, str) else views_raw

            if views:
                vdf = pd.DataFrame(views)
                if "instrument" in vdf.columns:
                    display_cols = ["instrument", "direction", "conviction", "target_weight"]
                    available = [c for c in display_cols if c in vdf.columns]
                    st.dataframe(vdf[available], width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Page: Trade History
# ---------------------------------------------------------------------------

def page_trades():
    st.header("Trade History")

    run_id = run_selector()
    if not run_id:
        return

    orders = load_trade_orders(run_id)
    if orders.empty:
        st.info("No trades for this run.")
        return

    st.metric("Total Trades", len(orders))
    st.metric("Total Costs", f"${orders['cost'].sum():,.0f}")

    # Trades over time
    orders["as_of"] = pd.to_datetime(orders["as_of"])
    trades_by_date = orders.groupby("as_of").agg(
        num_trades=("instrument", "count"),
        total_cost=("cost", "sum"),
    ).reset_index()

    fig = px.bar(trades_by_date, x="as_of", y="num_trades",
                 title="Trades per Rebalance",
                 labels={"as_of": "Date", "num_trades": "Number of Trades"})
    fig.update_layout(template="plotly_white", height=300)
    st.plotly_chart(fig, width="stretch")

    # Full trade log
    st.subheader("Trade Log")
    st.dataframe(orders, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Page: Ablation Results
# ---------------------------------------------------------------------------

def page_ablation():
    st.header("Ablation & Baseline Comparison")

    results = load_ablation_results()
    if not results:
        st.info("No ablation results found. Run the ablation experiments first.")
        st.code("python scripts/run_ablation.py --baselines-only")
        return

    # Build comparison table
    metrics_display = {
        "total_return": ("Total Return", ".2%"),
        "annualized_return": ("Ann. Return", ".2%"),
        "annualized_volatility": ("Ann. Volatility", ".2%"),
        "sharpe_ratio": ("Sharpe Ratio", ".2f"),
        "sortino_ratio": ("Sortino Ratio", ".2f"),
        "max_drawdown": ("Max Drawdown", ".2%"),
        "calmar_ratio": ("Calmar Ratio", ".2f"),
        "hit_rate": ("Hit Rate", ".2%"),
    }

    rows = []
    for metric_key, (label, fmt) in metrics_display.items():
        row = {"Metric": label}
        for variant, metrics in results.items():
            val = metrics.get(metric_key, 0)
            try:
                row[variant] = f"{val:{fmt}}"
            except (ValueError, TypeError):
                row[variant] = str(val)
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)

    # Bar chart comparison
    st.subheader("Sharpe Ratio Comparison")
    sharpe_data = {v: m.get("sharpe_ratio", 0) for v, m in results.items()}
    fig = px.bar(
        x=list(sharpe_data.keys()),
        y=list(sharpe_data.values()),
        labels={"x": "Strategy", "y": "Sharpe Ratio"},
        color=list(sharpe_data.values()),
        color_continuous_scale="RdYlGn",
    )
    fig.update_layout(template="plotly_white", height=400, showlegend=False)
    st.plotly_chart(fig, width="stretch")

    # Return comparison
    st.subheader("Total Return Comparison")
    return_data = {v: m.get("total_return", 0) * 100 for v, m in results.items()}
    fig2 = px.bar(
        x=list(return_data.keys()),
        y=list(return_data.values()),
        labels={"x": "Strategy", "y": "Total Return (%)"},
        color=list(return_data.values()),
        color_continuous_scale="RdYlGn",
    )
    fig2.update_layout(template="plotly_white", height=400, showlegend=False)
    st.plotly_chart(fig2, width="stretch")


# ---------------------------------------------------------------------------
# Page: System Architecture
# ---------------------------------------------------------------------------

def page_architecture():
    st.header("System Architecture")

    st.markdown("""
    ### Multi-Agent Workflow

    The system uses **4 information gathering agents** feeding into a **3-member council**
    that debates and produces portfolio decisions via a Delphi-method protocol.

    ```
    ┌─────────────────────────────────────────────────────┐
    │                INFORMATION GATHERING                 │
    │                                                      │
    │  Macro Sentinel     Market Technician                │
    │    (GPT-4o)          (Deterministic)                 │
    │                                                      │
    │  Narrative Analyst   Sentiment Scout                 │
    │    (Claude)            (Gemini)                      │
    └───────────────────────┬─────────────────────────────┘
                            │
                            ▼
    ┌─────────────────────────────────────────────────────┐
    │                   COUNCIL DEBATE                     │
    │                                                      │
    │  1. Strategist (GPT-4o)    → proposes thesis         │
    │  2. Contrarian (Claude)    → challenges thesis       │
    │  3. Synthesizer (Llama 70B)→ final decision          │
    │                                                      │
    │  Loop if conviction < 0.6 (max 2 rounds)             │
    └───────────────────────┬─────────────────────────────┘
                            │
                            ▼
    ┌─────────────────────────────────────────────────────┐
    │                    EXECUTION                         │
    │                                                      │
    │  Portfolio Constructor → Order Manager                │
    │  (constraints, risk)    (cost model, 30bps)          │
    └───────────────────────┬─────────────────────────────┘
                            │
                            ▼
    ┌─────────────────────────────────────────────────────┐
    │                    FEEDBACK                           │
    │                                                      │
    │  Backtest Evaluator (GPT-4o)                         │
    │  → scores each agent                                 │
    │  → injects feedback into future prompts              │
    └─────────────────────────────────────────────────────┘
    ```
    """)

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Investment Universe")
        universe = {
            "S&P 500": "SPY", "Nasdaq 100": "QQQ", "Russell 2000": "IWM",
            "US 10Y": "TLT", "US 2Y": "SHY", "Gold": "GLD",
            "Oil WTI": "USO", "DXY": "UUP", "VIX": "VIXY",
            "MSCI EM": "EEM", "Bitcoin": "BTC-USD",
        }
        udf = pd.DataFrame([
            {"Asset": k, "Ticker": v} for k, v in universe.items()
        ])
        st.dataframe(udf, width="stretch", hide_index=True)

    with col2:
        st.subheader("Model Assignments")
        models = [
            {"Agent": "Macro Sentinel", "Model": "GPT-4o", "Provider": "OpenAI"},
            {"Agent": "Market Technician", "Model": "Deterministic", "Provider": "None"},
            {"Agent": "Narrative Analyst", "Model": "Claude Sonnet", "Provider": "Anthropic"},
            {"Agent": "Sentiment Scout", "Model": "Gemini Flash", "Provider": "Google"},
            {"Agent": "Strategist", "Model": "GPT-4o", "Provider": "OpenAI"},
            {"Agent": "Contrarian", "Model": "Claude Sonnet", "Provider": "Anthropic"},
            {"Agent": "Synthesizer", "Model": "DeepSeek-V3", "Provider": "DeepSeek"},
            {"Agent": "Evaluator", "Model": "GPT-4o", "Provider": "OpenAI"},
        ]
        st.dataframe(pd.DataFrame(models), width="stretch", hide_index=True)

    st.divider()

    st.subheader("Key Design Decisions")
    st.markdown("""
    - **Model diversity**: Each agent uses a different LLM to reduce single-model bias
    - **Structured debate**: Delphi-method protocol with max 2 rounds, consensus threshold of 0.6
    - **Temporal discipline**: All data access filtered by `known_at <= as_of` — no look-ahead bias
    - **Deterministic technicals**: Market Technician has no LLM — isolates "does LLM reasoning help?"
    - **Weekly rebalancing**: Daily info gathering, weekly trading — narratives take days to play out
    - **30 bps round-trip costs**: Realistic transaction cost model with instrument-specific slippage
    """)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if page == "Portfolio Performance":
    page_portfolio()
elif page == "Agent Council":
    page_council()
elif page == "Trade History":
    page_trades()
elif page == "Ablation Results":
    page_ablation()
elif page == "System Architecture":
    page_architecture()
