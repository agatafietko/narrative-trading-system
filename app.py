"""Streamlit dashboard for the Narrative Trading System."""

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.state.store import DataStore

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Narrative Trading System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Global ── */
.stApp { background-color: #f0f4f8; }
.block-container { padding: 2rem 2.5rem 2rem 2.5rem; }

/* ── Hide default chrome ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* ── Sidebar background ── */
[data-testid="stSidebar"] > div:first-child {
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
}
[data-testid="stSidebar"] * { color: #cbd5e1 !important; }
[data-testid="stSidebar"] hr { border-color: #334155 !important; }

/* ── Nav: hide the widget label ("Navigation", "Select Run") but not options ── */
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-baseweb="radio"]) { display: none !important; }

/* ── Nav: hide only the radio circle visual inside each option ── */
[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio"] > div:first-child { display: none !important; }

/* ── Nav: style each option (the label with data-baseweb="radio") as a nav item ── */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
    display: flex !important;
    align-items: center !important;
    width: 100% !important;
    padding: 0.55rem 0.9rem !important;
    border-radius: 8px !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: #94a3b8 !important;
    cursor: pointer !important;
    border-left: 3px solid transparent !important;
    margin: 1px 0 !important;
    transition: background 0.18s ease, color 0.18s ease,
                border-color 0.18s ease, transform 0.15s ease !important;
}

/* ── Nav: hover state ── */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    background: rgba(255,255,255,0.07) !important;
    color: #e2e8f0 !important;
    border-left-color: rgba(59,130,246,0.5) !important;
    transform: translateX(3px) !important;
}

/* ── Nav: active/selected state ── */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
    background: rgba(59,130,246,0.18) !important;
    color: #93c5fd !important;
    border-left-color: #3b82f6 !important;
    font-weight: 600 !important;
    transform: translateX(3px) !important;
}


/* ── Run buttons (sidebar only) ── */
/* Reset every layer — wrapper div, button element, inner content div */
[data-testid="stSidebar"] [data-testid^="stBaseButton"],
[data-testid="stSidebar"] [data-testid^="stBaseButton"] > button,
[data-testid="stSidebar"] [data-testid^="stBaseButton"] > button > div {
    background: transparent !important; background-color: transparent !important;
    box-shadow: none !important; border: none !important;
    margin: 0 !important; padding: 0 !important;
}
/* Style the actual <button> element */
[data-testid="stSidebar"] [data-testid^="stBaseButton"] > button {
    display: flex !important; justify-content: space-between !important; align-items: center !important;
    width: 100% !important; padding: 0.45rem 0.85rem !important; border-radius: 8px !important;
    border-left: 3px solid transparent !important;
    font-size: 0.78rem !important; font-family: "SF Mono","Fira Code",monospace !important;
    cursor: pointer !important; letter-spacing: 0.01em !important;
    transition: background 0.15s ease, color 0.15s ease,
                border-color 0.15s ease, transform 0.13s ease !important;
}
/* Wrapper spacing */
[data-testid="stSidebar"] [data-testid^="stBaseButton"] {
    display: block !important; width: 100% !important; margin: 1px 0 !important;
}
/* Inactive — text matches sidebar background (ghost until hovered) */
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] > button {
    color: #1e293b !important;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] > button:hover {
    background: rgba(255,255,255,0.08) !important; color: #e2e8f0 !important;
    border-left-color: rgba(59,130,246,0.55) !important; transform: translateX(3px) !important;
}
/* Active */
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] > button {
    background: rgba(59,130,246,0.18) !important; color: #93c5fd !important;
    border-left-color: #3b82f6 !important; font-weight: 600 !important;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] > button:hover {
    background: rgba(59,130,246,0.26) !important; color: #bfdbfe !important;
}

/* ── Skeleton loading shimmer ── */
.skel-line {
    height: 30px; border-radius: 6px; margin: 3px 0;
    background: linear-gradient(90deg,
        rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.10) 50%, rgba(255,255,255,0.04) 100%);
    background-size: 200% 100%;
    animation: skel-shimmer 1.4s ease-in-out infinite;
}
@keyframes skel-shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

/* ── Metric cards ── */
.metric-card {
    background: white;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
    border-top: 3px solid #3b82f6;
    text-align: center;
}
.metric-card.green { border-top-color: #10b981; }
.metric-card.red   { border-top-color: #ef4444; }
.metric-card.amber { border-top-color: #f59e0b; }
.metric-value {
    font-size: 1.9rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.2;
    margin: 0.25rem 0;
}
.metric-value.green { color: #059669; }
.metric-value.red   { color: #dc2626; }
.metric-label {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
}

/* ── Section header ── */
.section-header {
    font-size: 1.4rem;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 1.25rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
}

/* ── Agent card ── */
.agent-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
}
.agent-badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
.badge-strategist  { background: #dbeafe; color: #1d4ed8; }
.badge-contrarian  { background: #fce7f3; color: #9d174d; }
.badge-synthesizer { background: #d1fae5; color: #065f46; }
.badge-risk        { background: #fee2e2; color: #991b1b; }
.badge-quant       { background: #fef9c3; color: #854d0e; }
.badge-skeptic     { background: #ede9fe; color: #5b21b6; }

/* ── Direction badges ── */
.dir-long  { background: #d1fae5; color: #065f46; padding: 2px 8px;
             border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
.dir-short { background: #fee2e2; color: #991b1b; padding: 2px 8px;
             border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
.dir-flat  { background: #f1f5f9; color: #475569; padding: 2px 8px;
             border-radius: 999px; font-size: 0.75rem; font-weight: 600; }

/* ── Conviction bar ── */
.conviction-bar-bg {
    background: #e2e8f0; border-radius: 999px;
    height: 6px; width: 100%; margin-top: 4px;
}
.conviction-bar-fill {
    background: #3b82f6; border-radius: 999px; height: 6px;
}

/* ── Info box ── */
.info-box {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    color: #1e40af;
    font-size: 0.875rem;
}

/* ── Architecture node ── */
.arch-node {
    background: white;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border-left: 4px solid #3b82f6;
    margin-bottom: 0.75rem;
}
.arch-node.gather { border-left-color: #8b5cf6; }
.arch-node.council { border-left-color: #f59e0b; }
.arch-node.execute { border-left-color: #10b981; }
.arch-node.feedback { border-left-color: #ef4444; }
.arch-title { font-weight: 700; font-size: 0.85rem; color: #0f172a; margin-bottom: 0.2rem; }
.arch-sub   { font-size: 0.78rem; color: #64748b; }

/* ── Streamlit overrides ── */
[data-testid="stMetricValue"] { font-size: 1.6rem !important; }
div[data-testid="stExpander"] {
    background: white;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    margin-bottom: 0.75rem;
}
</style>
""", unsafe_allow_html=True)

# ── Plotly theme ──────────────────────────────────────────────────────────────

CHART_LAYOUT = dict(
    template="plotly_white",
    font=dict(family="Inter, system-ui, sans-serif", size=12, color="#374151"),
    paper_bgcolor="white",
    plot_bgcolor="white",
    margin=dict(l=16, r=16, t=40, b=16),
    xaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False),
    yaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False),
    hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0", font_size=12),
)
BLUE    = "#3b82f6"
GREEN   = "#10b981"
RED     = "#ef4444"
AMBER   = "#f59e0b"
PURPLE  = "#8b5cf6"
PALETTE = [BLUE, GREEN, AMBER, PURPLE, RED, "#06b6d4", "#ec4899"]

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_resource
def get_store():
    return DataStore()

@st.cache_data(ttl=60)
def load_run_ids():
    return get_store().get_all_run_ids()

@st.cache_data(ttl=300)
def load_portfolio_history(run_id):
    return get_store().get_portfolio_history(run_id)

@st.cache_data(ttl=60)
def load_council_votes(run_id):
    return get_store().get_council_votes_for_run(run_id)

@st.cache_data(ttl=300)
def load_trade_orders(run_id):
    return get_store().get_trade_orders_for_run(run_id)

@st.cache_data(ttl=300)
def load_ablation_results():
    p = Path("data/ablation_results.json")
    if not p.exists():
        return None
    raw = json.loads(p.read_text())
    # Strip metadata keys (strings/non-dicts) — only keep strategy result dicts
    return {k: v for k, v in raw.items() if isinstance(v, dict)}

# ── Sidebar helpers ───────────────────────────────────────────────────────────

def parse_run_datetime(run_id: str):
    """Parse run_20260503_165514_abc → datetime object."""
    from datetime import datetime
    try:
        parts = run_id.split("_")
        return datetime.strptime(f"{parts[1]}{parts[2]}", "%Y%m%d%H%M%S")
    except Exception:
        return None

def run_label(run_id: str) -> str:
    dt = parse_run_datetime(run_id)
    return dt.strftime("%b %d, %Y  %H:%M") if dt else run_id

def run_list_label(run_id: str) -> str:
    """Format for the run list: 'May 03  18:27   +16.9%'"""
    dt = parse_run_datetime(run_id)
    date_str = dt.strftime("%b %d  %H:%M") if dt else run_id[-8:]
    try:
        h = load_portfolio_history(run_id)
        if not h.empty and len(h) >= 2:
            ret = h["nav"].iloc[-1] / h["nav"].iloc[0] - 1
            sign = "+" if ret >= 0 else ""
            return f"{date_str}   {sign}{ret:.1%}"
    except Exception:
        pass
    return date_str

@st.cache_data(ttl=300)
def get_valid_runs(run_ids_tuple: tuple):
    """Return list of (run_id, dt, ret, final_nav, sharpe, mdd) for displayable runs."""
    result = []
    for rid in run_ids_tuple:
        dt = parse_run_datetime(rid)
        if not dt:
            continue
        try:
            h = load_portfolio_history(rid)
            if h.empty or len(h) < 2:
                continue
            nav = h["nav"]
            ret = float(nav.iloc[-1] / nav.iloc[0] - 1)
            wr  = nav.pct_change().dropna()
            sharpe = float(wr.mean() / wr.std() * (52 ** 0.5)) if wr.std() > 0 else 0.0
            mdd = float(((nav / nav.cummax()) - 1).min())
            result.append((rid, dt, ret, float(nav.iloc[-1]), sharpe, mdd))
        except Exception:
            continue
        if len(result) >= 8:
            break
    return result

# ── Sidebar ───────────────────────────────────────────────────────────────────

NAV_OPTIONS = [
    "🏠  Overview",
    "📊  Portfolio Performance",
    "⚖️  Jury Duty",
    "📋  Trade History",
    "🔬  Ablation Results",
    "🏗️  Architecture",
]

if "selected_run" not in st.session_state:
    st.session_state.selected_run = None
if "page" not in st.session_state:
    st.session_state.page = NAV_OPTIONS[0]

with st.sidebar:
    st.markdown("""
    <div style='padding: 1rem 0 0.5rem 0;'>
        <div style='font-size:1.35rem; font-weight:800; color:#f8fafc; letter-spacing:-0.02em;'>
            📈 NarrativeTrader
        </div>
        <div style='font-size:0.75rem; color:#94a3b8; margin-top:0.2rem;'>
            Multi-Agent Portfolio System
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    page_idx = NAV_OPTIONS.index(st.session_state.page) if st.session_state.page in NAV_OPTIONS else 0
    page = st.radio(
        "Navigation",
        options=NAV_OPTIONS,
        index=page_idx,
        label_visibility="collapsed",
    )
    if page != st.session_state.page:
        st.session_state.page = page

    st.divider()

    run_ids = load_run_ids()

    if run_ids:
        # Initialise default selection
        if st.session_state.selected_run not in run_ids:
            st.session_state.selected_run = run_ids[0]

        # Section label
        st.markdown("""
        <div style='font-size:0.7rem;font-weight:700;text-transform:uppercase;
                     letter-spacing:0.08em;color:#64748b;margin-bottom:0.35rem;'>
            Recent Runs
        </div>
        """, unsafe_allow_html=True)

        # Skeleton placeholder — replaced immediately once data is ready
        skel = st.empty()
        skel.markdown("""
        <div style="padding:0 0.1rem;">
          <div class="skel-line"></div>
          <div class="skel-line" style="opacity:.7"></div>
          <div class="skel-line" style="opacity:.4"></div>
        </div>
        """, unsafe_allow_html=True)

        # Load valid runs (cached after first call)
        valid_runs = get_valid_runs(tuple(run_ids[:15]))
        skel.empty()

        if not valid_runs:
            selected_run = st.session_state.selected_run
            st.markdown("<div style='color:#f87171;font-size:0.78rem;'>No completed runs yet.</div>",
                        unsafe_allow_html=True)
        else:
            valid_ids = [r[0] for r in valid_runs]
            if st.session_state.selected_run not in valid_ids:
                st.session_state.selected_run = valid_ids[0]

            for (rid, dt, ret, final_nav, sharpe, mdd) in valid_runs:
                is_active = rid == st.session_state.selected_run
                date_str  = dt.strftime("%b %d  %H:%M")
                ret_str   = f"{ret:+.1%}"
                # Use Unicode hair-space U+200A to space date and return inside the button label
                label = f"{date_str} {ret_str}"
                if st.button(
                    label,
                    key=f"run_{rid}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state.selected_run = rid
                    st.session_state.page = "📊  Portfolio Performance"
                    st.rerun()

            selected_run = st.session_state.selected_run

    else:
        selected_run = None
        st.markdown(
            "<div style='color:#f87171;font-size:0.78rem;'>"
            "No runs found. Trigger a GitHub Actions run.</div>",
            unsafe_allow_html=True,
        )

    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True, help="Clear cached data and reload from database"):
        st.cache_data.clear()
        st.rerun()
    st.markdown(
        "<div style='font-size:0.7rem; color:#475569;'>Data refreshes every 5 min<br>"
        "<a href='https://github.com/agatafietko/narrative-trading-system' "
        "style='color:#60a5fa;'>View on GitHub ↗</a></div>",
        unsafe_allow_html=True,
    )

# ── Helpers ───────────────────────────────────────────────────────────────────

def metric_card(label, value, color="blue"):
    st.markdown(f"""
    <div class="metric-card {color if color != 'blue' else ''}">
        <div class="metric-label">{label}</div>
        <div class="metric-value {color if color in ('green','red') else ''}">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def section(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)

def no_data(msg, cmd=None):
    html = f'<div class="info-box">{msg}'
    if cmd:
        html += f'<br><br><code style="background:#dbeafe;padding:2px 6px;border-radius:4px;">{cmd}</code>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

# ── Page: Overview ────────────────────────────────────────────────────────────

def page_overview():
    st.markdown("""
    <div style='margin-bottom:2rem;'>
        <h1 style='font-size:2rem;font-weight:800;color:#0f172a;margin:0;'>
            Narrative-to-Portfolio Trading System
        </h1>
        <p style='color:#64748b;margin-top:0.4rem;font-size:1rem;'>
            A multi-agent LLM system that reads market narratives and turns them into portfolio decisions.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Top-level stats from all runs
    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Total Runs", str(len(run_ids)) if run_ids else "0")
    with c2: metric_card("Instruments", "11")
    with c3: metric_card("LLM Agents", "7")
    with c4: metric_card("Backtest Period", "Jan–Apr 2026")

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns([3, 2])

    with col_l:
        section("System Pipeline")
        stages = [
            ("gather",   "📡 Information Gathering",  "Macro Sentinel · Market Technician · Narrative Analyst · Sentiment Scout"),
            ("council",  "⚖️  Council Debate",         "Strategist (GPT-4o) → Contrarian (Claude) → Synthesizer (DeepSeek) — Delphi protocol, max 2 rounds"),
            ("execute",  "🚀 Execution",               "Portfolio Constructor applies constraints · Order Manager applies 30 bps cost model"),
            ("feedback", "🔁 Feedback Loop",           "Backtest Evaluator scores each agent · injects feedback into future prompts"),
        ]
        for cls, title, sub in stages:
            st.markdown(f"""
            <div class="arch-node {cls}">
                <div class="arch-title">{title}</div>
                <div class="arch-sub">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

    with col_r:
        section("Model Assignments")
        models_df = pd.DataFrame([
            {"Agent": "Macro Sentinel",    "Model": "GPT-4o",          "Role": "Gatherer"},
            {"Agent": "Market Technician", "Model": "Deterministic",   "Role": "Gatherer"},
            {"Agent": "Narrative Analyst", "Model": "Claude Sonnet",   "Role": "Gatherer"},
            {"Agent": "Sentiment Scout",   "Model": "Gemini Flash",    "Role": "Gatherer"},
            {"Agent": "Strategist",        "Model": "GPT-4o",          "Role": "Council"},
            {"Agent": "Contrarian",        "Model": "Claude Sonnet",   "Role": "Council"},
            {"Agent": "Synthesizer",       "Model": "GPT-4o mini",     "Role": "Council"},
            {"Agent": "Evaluator",         "Model": "GPT-4o",          "Role": "Feedback"},
        ])
        st.dataframe(models_df, hide_index=True, use_container_width=True,
                     column_config={"Role": st.column_config.TextColumn(width="small")})

        section("Investment Universe")
        universe_df = pd.DataFrame([
            {"Asset": "S&P 500",    "Ticker": "SPY",     "Class": "Equity"},
            {"Asset": "Nasdaq 100", "Ticker": "QQQ",     "Class": "Equity"},
            {"Asset": "Russell 2000","Ticker": "IWM",    "Class": "Equity"},
            {"Asset": "MSCI EM",    "Ticker": "EEM",     "Class": "Equity"},
            {"Asset": "US 10Y",     "Ticker": "TLT",     "Class": "Bond"},
            {"Asset": "US 2Y",      "Ticker": "SHY",     "Class": "Bond"},
            {"Asset": "Gold",       "Ticker": "GLD",     "Class": "Commodity"},
            {"Asset": "Oil WTI",    "Ticker": "USO",     "Class": "Commodity"},
            {"Asset": "DXY",        "Ticker": "UUP",     "Class": "FX"},
            {"Asset": "VIX",        "Ticker": "VIXY",    "Class": "Vol"},
            {"Asset": "Bitcoin",    "Ticker": "BTC-USD", "Class": "Crypto"},
        ])
        st.dataframe(universe_df, hide_index=True, use_container_width=True,
                     column_config={"Class": st.column_config.TextColumn(width="small")})


# ── Page: Portfolio Performance ───────────────────────────────────────────────

def page_portfolio():
    st.markdown("<h2 style='color:#0f172a;font-weight:800;margin-bottom:1.5rem;'>Portfolio Performance</h2>",
                unsafe_allow_html=True)

    if not selected_run:
        no_data("No runs found. Trigger a GitHub Actions run first.")
        return

    history = load_portfolio_history(selected_run)
    if history.empty:
        no_data("No portfolio data for this run.")
        return

    # Metrics row
    total_ret = history["nav"].iloc[-1] / history["nav"].iloc[0] - 1
    returns   = history["nav"].pct_change().dropna()
    sharpe    = (returns.mean() / returns.std() * (252 ** 0.5)) if returns.std() > 0 else 0
    peak      = history["nav"].cummax()
    max_dd    = ((history["nav"] - peak) / peak).min()
    total_cost = history["total_cost_incurred"].iloc[-1]

    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Total Return",  f"{total_ret:+.2%}", "green" if total_ret >= 0 else "red")
    with c2: metric_card("Sharpe Ratio",  f"{sharpe:.2f}",     "green" if sharpe >= 1 else "amber")
    with c3: metric_card("Max Drawdown",  f"{max_dd:.2%}",     "red")
    with c4: metric_card("Total Costs",   f"${total_cost:,.0f}")

    st.markdown("<br>", unsafe_allow_html=True)

    # NAV chart
    section("Net Asset Value")
    fig = go.Figure()
    # Shaded area under the line
    fig.add_trace(go.Scatter(
        x=history["as_of"], y=history["nav"],
        fill="tozeroy", fillcolor="rgba(59,130,246,0.07)",
        mode="lines", name="Portfolio NAV",
        line=dict(color=BLUE, width=2.5),
        hovertemplate="<b>%{x|%b %d, %Y}</b><br>NAV: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(
        y=1_000_000, line_dash="dot", line_color="#94a3b8", line_width=1.5,
        annotation_text="Initial Capital  $1M", annotation_position="bottom right",
        annotation_font_color="#94a3b8",
    )
    fig.update_layout(**CHART_LAYOUT, height=380,
                      yaxis_title="NAV ($)", xaxis_title="")
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")

    # Holdings + table
    latest      = history.iloc[-1]
    weights_raw = latest["weights"]
    weights     = json.loads(weights_raw) if isinstance(weights_raw, str) else weights_raw

    if weights:
        cash = float(latest.get("cash_weight") or 0)
        display_w = {**weights}
        if cash >= 0.005:
            display_w["CASH"] = cash
        display_w = {k: v for k, v in display_w.items() if abs(v) >= 0.005}

        col_pie, col_tbl = st.columns([1, 1])

        with col_pie:
            section("Current Allocation")
            fig_pie = go.Figure(go.Pie(
                labels=list(display_w.keys()),
                values=[abs(v) for v in display_w.values()],
                hole=0.5,
                marker_colors=PALETTE,
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>",
            ))
            fig_pie.update_layout(
                **{k: v for k, v in CHART_LAYOUT.items() if k != "xaxis" and k != "yaxis"},
                height=320,
                showlegend=False,
                annotations=[dict(text=f"<b>{latest['as_of']}</b>" if isinstance(latest['as_of'], str)
                                  else f"<b>{latest['as_of'].strftime('%b %d')}</b>",
                                  x=0.5, y=0.5, font_size=12, showarrow=False,
                                  font_color="#64748b")],
            )
            st.plotly_chart(fig_pie, width="stretch")

        with col_tbl:
            section("Holdings Detail")
            rows = sorted(display_w.items(), key=lambda x: -abs(x[1]))
            tdf = pd.DataFrame([
                {"Instrument": k,
                 "Weight": f"{v:.1%}",
                 "$ Value": f"${abs(v) * float(latest['nav']):,.0f}",
                 "Side": "Long" if v > 0 else "Short" if v < 0 else "Cash"}
                for k, v in rows
            ])
            st.dataframe(tdf, hide_index=True, use_container_width=True,
                         column_config={"Side": st.column_config.TextColumn(width="small")})

    # ── Explain this performance ───────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    perf_cache_key = f"perf_explain_{selected_run}"
    if perf_cache_key not in st.session_state:
        st.session_state[perf_cache_key] = None

    if st.button("🧠 Explain this performance", key=f"btn_{perf_cache_key}"):
        perf_data = {
            "run_id": selected_run,
            "total_return": float(total_ret),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_dd),
            "total_cost_usd": float(total_cost),
            "initial_capital": 1_000_000,
        }
        with st.spinner("Analyzing performance..."):
            try:
                from src.agents.analysis.results_analyst import ResultsAnalyst
                analyst = ResultsAnalyst()
                st.session_state[perf_cache_key] = analyst.explain("performance", perf_data)
            except Exception as e:
                st.session_state[perf_cache_key] = f"Analysis unavailable: {e}"

    if st.session_state[perf_cache_key]:
        st.info(st.session_state[perf_cache_key])


# ── Page: Jury Duty ───────────────────────────────────────────────────────────

def page_jury():
    st.markdown("<h2 style='color:#0f172a;font-weight:800;margin-bottom:1.5rem;'>Jury Duty</h2>",
                unsafe_allow_html=True)

    if not selected_run:
        no_data("No runs found.")
        return

    votes = load_council_votes(selected_run)
    if not votes:
        # Try to find another run that has council votes
        all_runs = load_run_ids()
        run_with_votes = None
        for rid in all_runs:
            if rid != selected_run:
                candidate = load_council_votes(rid)
                if candidate:
                    run_with_votes = rid
                    votes = candidate
                    break

        if not votes:
            no_data(
                "No council votes in this run. The full multi-agent system hasn't run yet.",
                "Actions → Daily Backtest Run → Run workflow → full_system"
            )
            return

        st.info(
            f"No council votes for the selected run — showing votes from "
            f"**`{run_with_votes}`** instead (most recent run with council data)."
        )

    dates = sorted(set(v["as_of"] for v in votes), reverse=True)
    selected_date = st.selectbox("Debate date", dates,
                                 format_func=lambda d: f"Week of {d[:10]}")
    date_votes = [v for v in votes if v["as_of"] == selected_date]

    # Conviction summary bar
    if date_votes:
        convictions = {v["agent_name"]: v.get("overall_conviction", 0) for v in date_votes}
        avg_conviction = sum(convictions.values()) / len(convictions)
        consensus = avg_conviction >= 0.6

        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            metric_card("Avg Conviction", f"{avg_conviction:.0%}",
                        "green" if consensus else "amber")
        with col_b:
            metric_card("Consensus", "Reached ✓" if consensus else "Debated ↻",
                        "green" if consensus else "amber")
        with col_c:
            metric_card("Agents", f"{len(date_votes)} / 6 voted")

    st.markdown("<br>", unsafe_allow_html=True)

    agent_cfg = {
        "strategist":         ("🎯", "Strategist",         "badge-strategist", "Proposes investment thesis based on all signals"),
        "contrarian":         ("⚡", "Contrarian",         "badge-contrarian",  "Challenges the thesis — finds crowded trades and missed risks"),
        "risk_manager":       ("🛡️", "Risk Manager",       "badge-risk",        "Stress-tests tail risk and concentration"),
        "quant":              ("📐", "Quant",              "badge-quant",       "Pure signal-driven, ignores narrative"),
        "behavioral_skeptic": ("🧠", "Behavioral Skeptic", "badge-skeptic",     "Challenges crowd positioning and sentiment consensus"),
        "synthesizer":        ("⚖️", "Synthesizer",        "badge-synthesizer", "Mediates and produces the final portfolio decision"),
    }

    for vote in date_votes:
        agent = vote["agent_name"]
        conviction = vote.get("overall_conviction", 0)
        model = vote.get("model_used", "unknown").split("/")[-1]
        icon, label, badge_cls, role_desc = agent_cfg.get(
            agent, ("🤖", agent.title(), "badge-strategist", ""))

        bar_w = int(conviction * 100)
        bar_color = GREEN if conviction >= 0.6 else AMBER if conviction >= 0.4 else RED

        with st.expander(f"{icon}  {label}  ·  {conviction:.0%} conviction  ·  {model}", expanded=True):
            hcol, _ = st.columns([3, 1])
            with hcol:
                st.markdown(f"""
                <span class="agent-badge {badge_cls}">{label}</span>
                <span style="font-size:0.8rem;color:#64748b;margin-left:0.5rem;">{role_desc}</span>
                <div class="conviction-bar-bg">
                    <div class="conviction-bar-fill" style="width:{bar_w}%;background:{bar_color};"></div>
                </div>
                """, unsafe_allow_html=True)

            summary = vote.get("summary", "")
            if summary:
                st.markdown(f"> {summary}")

            views_raw = vote.get("views", "[]")
            views = json.loads(views_raw) if isinstance(views_raw, str) else views_raw
            if views:
                vdf = pd.DataFrame(views)
                display_cols = [c for c in ["instrument", "direction", "conviction", "target_weight"] if c in vdf.columns]
                if display_cols:
                    st.dataframe(vdf[display_cols], hide_index=True, use_container_width=True)

    # ── Explain this jury verdict ──────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    cache_key = f"jury_explain_{selected_run}_{selected_date}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = None

    if date_votes:
        if st.button("🧠 Explain this jury verdict", key=f"btn_{cache_key}"):
            jury_data = {
                "selected_date": selected_date,
                "avg_conviction": avg_conviction,
                "consensus_reached": consensus,
                "votes": [
                    {
                        "agent_name": v["agent_name"],
                        "overall_conviction": v.get("overall_conviction", 0),
                        "summary": v.get("summary", ""),
                        "model_used": v.get("model_used", ""),
                    }
                    for v in date_votes
                ],
            }
            with st.spinner("Analyzing jury verdict..."):
                try:
                    from src.agents.analysis.results_analyst import ResultsAnalyst
                    analyst = ResultsAnalyst()
                    st.session_state[cache_key] = analyst.explain("jury_duty", jury_data)
                except Exception as e:
                    st.session_state[cache_key] = f"Analysis unavailable: {e}"

        if st.session_state[cache_key]:
            st.info(st.session_state[cache_key])


# ── Page: Trade History ───────────────────────────────────────────────────────

def page_trades():
    st.markdown("<h2 style='color:#0f172a;font-weight:800;margin-bottom:1.5rem;'>Trade History</h2>",
                unsafe_allow_html=True)

    if not selected_run:
        no_data("No runs found.")
        return

    orders = load_trade_orders(selected_run)
    if orders.empty:
        no_data("No trades for this run.")
        return

    orders["as_of"] = pd.to_datetime(orders["as_of"])
    buys  = orders[orders["direction"] == "buy"]
    sells = orders[orders["direction"] == "sell"]

    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Total Trades",   str(len(orders)))
    with c2: metric_card("Buy Orders",     str(len(buys)),  "green")
    with c3: metric_card("Sell Orders",    str(len(sells)), "red")
    with c4: metric_card("Total Costs",    f"${orders['cost'].sum():,.0f}", "amber")

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns([3, 2])

    with col_l:
        section("Trade Activity Over Time")
        by_date = orders.groupby(["as_of", "direction"]).size().reset_index(name="count")
        fig = px.bar(by_date, x="as_of", y="count", color="direction",
                     color_discrete_map={"buy": GREEN, "sell": RED},
                     labels={"as_of": "", "count": "Number of Trades", "direction": "Side"},
                     barmode="group")
        fig.update_layout(**CHART_LAYOUT, height=320, legend=dict(orientation="h", y=1.1))
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, width="stretch")

    with col_r:
        section("Cost Breakdown by Instrument")
        cost_by_inst = orders.groupby("instrument")["cost"].sum().sort_values(ascending=True)
        fig2 = go.Figure(go.Bar(
            x=cost_by_inst.values, y=cost_by_inst.index,
            orientation="h",
            marker_color=AMBER, marker_line_width=0,
            hovertemplate="<b>%{y}</b><br>Cost: $%{x:,.0f}<extra></extra>",
        ))
        fig2.update_layout(**CHART_LAYOUT, height=320,
                           xaxis_title="Total Cost ($)", yaxis_title="")
        fig2.update_xaxes(tickprefix="$", tickformat=",.0f")
        st.plotly_chart(fig2, width="stretch")

    section("Full Trade Log")
    display_orders = orders.copy()
    display_orders["cost"] = display_orders["cost"].apply(lambda x: f"${x:,.2f}")
    display_orders["dollar_amount"] = display_orders["dollar_amount"].apply(lambda x: f"${abs(x):,.0f}")
    display_orders["weight_delta"] = display_orders["weight_delta"].apply(lambda x: f"{x:+.2%}")
    display_orders["as_of"] = display_orders["as_of"].dt.strftime("%Y-%m-%d")
    st.dataframe(display_orders, hide_index=True, use_container_width=True)


# ── Page: Ablation Results ────────────────────────────────────────────────────

def page_ablation():
    st.markdown("<h2 style='color:#0f172a;font-weight:800;margin-bottom:1.5rem;'>Ablation & Baseline Comparison</h2>",
                unsafe_allow_html=True)

    results = load_ablation_results()
    if not results:
        no_data("No ablation results found. Run the ablation experiments first.",
                "Actions → Run workflow → baselines_only")
        return

    # Strategy name cleanup
    label_map = {
        "sixty_forty": "60/40",
        "sixty_forty_2026": "60/40",
        "equal_weight": "Equal Weight",
        "equal_weight_2026": "Equal Weight",
        "technical_momentum": "Tech. Momentum",
        "random": "Random",
        "random_2026": "Random",
        "full": "Full System",
        "full_system": "Full System",
        "no_narrative": "No Narrative",
        "no_sentiment": "No Sentiment",
        "no_feedback": "No Feedback",
        "homogeneous": "Homogeneous GPT-4o",
        "minimal": "Single Agent",
        "single_agent_minimal": "Single Agent",
    }

    metrics_cfg = {
        "total_return":         ("Total Return",     ".1%",  True),
        "annualized_return":    ("Ann. Return",      ".1%",  True),
        "annualized_volatility":("Ann. Volatility",  ".1%",  False),
        "sharpe_ratio":         ("Sharpe Ratio",     ".2f",  True),
        "sortino_ratio":        ("Sortino Ratio",    ".2f",  True),
        "max_drawdown":         ("Max Drawdown",     ".1%",  False),
        "calmar_ratio":         ("Calmar Ratio",     ".2f",  True),
        "hit_rate":             ("Hit Rate",         ".1%",  True),
    }

    strategies  = list(results.keys())
    clean_names = [label_map.get(s, s.replace("_", " ").title()) for s in strategies]

    def _val(strat, key, default=0):
        """Get a numeric metric, coercing None → default."""
        v = results[strat].get(key, default)
        return default if v is None else v

    # Sharpe bar chart — handles nulls and many strategies cleanly
    section("Sharpe Ratio by Strategy")
    sharpe_rows = []
    for strat, name in zip(strategies, clean_names):
        raw = results[strat].get("sharpe_ratio")
        sharpe_rows.append({
            "Strategy": name,
            "Sharpe": raw if raw is not None else float("nan"),
            "Available": raw is not None,
            "Label": f"{raw:.2f}" if raw is not None else "n/a†",
        })
    sharpe_rows.sort(key=lambda r: r["Sharpe"] if not (r["Sharpe"] != r["Sharpe"]) else -999)
    sdf2 = pd.DataFrame(sharpe_rows)
    bar_colors = [GREEN if s >= 0.5 else AMBER if s >= 0 else RED
                  for s in sdf2["Sharpe"].fillna(0)]
    fig_sr = go.Figure(go.Bar(
        x=sdf2["Sharpe"].fillna(0),
        y=sdf2["Strategy"],
        orientation="h",
        marker_color=bar_colors,
        marker_line_width=0,
        text=sdf2["Label"],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Sharpe: %{text}<extra></extra>",
    ))
    fig_sr.add_vline(x=0, line_color="#94a3b8", line_width=1)
    sr_layout = {**CHART_LAYOUT}
    sr_layout["height"] = max(280, len(strategies) * 42)
    sr_layout["xaxis_title"] = "Sharpe Ratio"
    sr_layout["yaxis"] = dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False, autorange="reversed")
    sr_layout["margin"] = dict(l=0, r=60, t=10, b=30)
    fig_sr.update_layout(**sr_layout)
    st.plotly_chart(fig_sr, width="stretch")
    st.caption("† n/a indicates fewer than 8 weekly rebalances — Sharpe shown as 0 for bar scale only.")

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns(2)

    with col_l:
        section("Return vs Max Drawdown")
        scatter_data = []
        for strat, name in zip(strategies, clean_names):
            tr  = _val(strat, "total_return") * 100
            mdd = abs(_val(strat, "max_drawdown")) * 100
            scatter_data.append({
                "Strategy": name,
                "Total Return (%)": tr,
                "Max Drawdown (%)": mdd,
                "Return/Risk": tr / mdd if mdd > 0 else 0,
            })
        sdf = pd.DataFrame(scatter_data)
        fig = px.scatter(
            sdf,
            x="Max Drawdown (%)",
            y="Total Return (%)",
            text="Strategy",
            size=[max(abs(r), 0.5) for r in sdf["Return/Risk"]],
            color="Return/Risk",
            color_continuous_scale=["#ef4444", "#f59e0b", "#10b981"],
            size_max=40,
            hover_data={"Strategy": True, "Total Return (%)": ":.2f", "Max Drawdown (%)": ":.2f"},
        )
        fig.add_hline(y=0, line_dash="dash", line_color="#94a3b8", line_width=1)
        fig.update_traces(textposition="top center", marker_line_width=0)
        fig.update_layout(
            **CHART_LAYOUT, height=380,
            coloraxis_showscale=False,
            xaxis_title="Max Drawdown (%)",
            yaxis_title="Total Return (%)",
        )
        st.plotly_chart(fig, width="stretch")

    with col_r:
        section("Total Return Comparison")
        ret_data = [(label_map.get(s, s), _val(s, "total_return") * 100) for s in strategies]
        ret_data.sort(key=lambda x: x[1], reverse=True)
        fig2 = go.Figure(go.Bar(
            x=[r[1] for r in ret_data],
            y=[r[0] for r in ret_data],
            orientation="h",
            marker_color=[GREEN if r[1] >= 0 else RED for r in ret_data],
            marker_line_width=0,
            text=[f"{r[1]:.1f}%" for r in ret_data],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Return: %{x:.1f}%<extra></extra>",
        ))
        fig2.update_layout(**CHART_LAYOUT, height=360, xaxis_title="Total Return (%)")
        st.plotly_chart(fig2, width="stretch")

    # Full metrics table
    section("Full Metrics Table")
    rows = []
    for metric_key, (label, fmt, _) in metrics_cfg.items():
        row = {"Metric": label}
        for strat, name in zip(strategies, clean_names):
            val = _val(strat, metric_key)
            try:
                row[name] = f"{val:{fmt}}"
            except (ValueError, TypeError):
                row[name] = "—"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ── Explain these results ──────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    abl_cache_key = "ablation_explain"
    if abl_cache_key not in st.session_state:
        st.session_state[abl_cache_key] = None

    if st.button("🧠 Explain these results", key=f"btn_{abl_cache_key}"):
        with st.spinner("Analyzing ablation results..."):
            try:
                from src.agents.analysis.results_analyst import ResultsAnalyst
                analyst = ResultsAnalyst()
                st.session_state[abl_cache_key] = analyst.explain("ablation", results)
            except Exception as e:
                st.session_state[abl_cache_key] = f"Analysis unavailable: {e}"

    if st.session_state[abl_cache_key]:
        st.info(st.session_state[abl_cache_key])


# ── Page: Architecture ────────────────────────────────────────────────────────

def page_architecture():
    st.markdown("<h2 style='color:#0f172a;font-weight:800;margin-bottom:1.5rem;'>System Architecture</h2>",
                unsafe_allow_html=True)

    col_l, col_r = st.columns([3, 2])

    with col_l:
        section("Agent Pipeline")
        pipeline = [
            ("gather",   "📡", "Information Gathering",  [
                ("Macro Sentinel",    "GPT-4o",        "Reads FRED macro data — rates, inflation, yield curve, DXY"),
                ("Market Technician", "Deterministic", "Computes RSI, MACD, Bollinger Bands, trend, momentum"),
                ("Narrative Analyst", "Claude Sonnet", "Extracts dominant narratives from news articles and GDELT"),
                ("Sentiment Scout",   "Gemini Flash",  "Scores fear/greed from Reddit and social signals"),
            ]),
            ("council",  "⚖️",  "Council Debate (Delphi Protocol)", [
                ("Strategist",  "GPT-4o",      "Proposes investment thesis — views per instrument with conviction"),
                ("Contrarian",  "Claude Sonnet","Challenges thesis — finds crowded trades and missed risks"),
                ("Synthesizer", "GPT-4o mini", "Mediates and produces final weights. Loops if conviction < 0.6"),
            ]),
            ("execute",  "🚀", "Execution", [
                ("Portfolio Constructor", "—", "Applies position limits (25%), equity cap (40%), 5% cash buffer"),
                ("Order Manager",         "—", "Executes trades at 30 bps round-trip + instrument slippage"),
            ]),
            ("feedback", "🔁", "Feedback Loop", [
                ("Backtest Evaluator", "GPT-4o", "Scores each agent's accuracy · injects scores into future prompts"),
            ]),
        ]
        for stage_cls, icon, stage_name, agents in pipeline:
            st.markdown(f"""
            <div class="arch-node {stage_cls}">
                <div class="arch-title">{icon} {stage_name}</div>
            </div>
            """, unsafe_allow_html=True)
            for agent, model, desc in agents:
                with st.container(border=True):
                    left, right = st.columns([3, 1])
                    with left:
                        st.markdown(f"**{agent}**")
                        st.caption(desc)
                    with right:
                        if model != "—":
                            st.markdown(
                                f'<div style="text-align:right;font-size:0.75rem;'
                                f'color:#64748b;padding-top:4px;">{model}</div>',
                                unsafe_allow_html=True,
                            )

    with col_r:
        section("Key Design Decisions")
        decisions = [
            ("🎭", "Model Diversity",      "Each agent uses a different LLM (OpenAI / Anthropic / Google / DeepSeek) to prevent single-model groupthink."),
            ("🔒", "No Look-Ahead Bias",   "All data access uses known_at ≤ as_of filtering. Point-in-time queries are enforced at the architecture level."),
            ("📐", "Structured Debate",    "Delphi-method council: Strategist proposes → Contrarian challenges → Synthesizer mediates. Max 2 rounds, threshold 0.6."),
            ("🧪", "Ablation Design",      "Market Technician is fully deterministic — isolates 'does LLM reasoning add value?' from 'does this data source help?'"),
            ("💰", "Realistic Costs",      "30 bps round-trip + 5 bps slippage for illiquid instruments. Weekly rebalancing to avoid over-trading."),
        ]
        for icon, title, body in decisions:
            st.markdown(f"""
            <div style="background:white;border-radius:10px;padding:0.9rem 1rem;
                        margin-bottom:0.6rem;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
                <div style="font-weight:700;font-size:0.875rem;color:#0f172a;margin-bottom:0.3rem;">
                    {icon} {title}
                </div>
                <div style="font-size:0.8rem;color:#64748b;line-height:1.5;">{body}</div>
            </div>
            """, unsafe_allow_html=True)

        section("Backtest Parameters")
        params = {
            "Initial Capital": "$1,000,000",
            "Period": "Jan 2026 – Apr 2026",
            "Rebalance": "Weekly (Friday close)",
            "Transaction Cost": "30 bps round-trip",
            "Max Position": "25% single asset",
            "Equity Cap": "40% total",
            "Cash Buffer": "≥ 5%",
        }
        for k, v in params.items():
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;padding:0.4rem 0;
                        border-bottom:1px solid #f1f5f9;font-size:0.85rem;">
                <span style="color:#64748b;">{k}</span>
                <span style="font-weight:600;color:#0f172a;">{v}</span>
            </div>
            """, unsafe_allow_html=True)


# ── Run Analysis ──────────────────────────────────────────────────────────────

def render_run_analysis_button():
    """Render the full-run analysis button and result panel, visible on all tabs."""
    if not selected_run:
        return

    run_cache_key = f"full_run_explain_{selected_run}"
    if run_cache_key not in st.session_state:
        st.session_state[run_cache_key] = None

    col_btn, _ = st.columns([2, 5])
    with col_btn:
        if st.button("📋 Analyze this run", key=f"btn_{run_cache_key}", use_container_width=True):
            votes = load_council_votes(selected_run)
            history = load_portfolio_history(selected_run)

            full_data = {
                "run_id": selected_run,
                "votes": [
                    {
                        "agent_name": v["agent_name"],
                        "overall_conviction": v.get("overall_conviction", 0),
                        "summary": v.get("summary", ""),
                    }
                    for v in votes
                ] if votes else [],
                "performance": {},
            }

            if not history.empty and len(history) >= 2:
                total_ret = history["nav"].iloc[-1] / history["nav"].iloc[0] - 1
                returns = history["nav"].pct_change().dropna()
                sharpe = float(returns.mean() / returns.std() * (252 ** 0.5)) if returns.std() > 0 else 0
                peak = history["nav"].cummax()
                max_dd = float(((history["nav"] - peak) / peak).min())
                full_data["performance"] = {
                    "total_return": float(total_ret),
                    "sharpe_ratio": sharpe,
                    "max_drawdown": max_dd,
                }

            with st.spinner("Writing run analysis..."):
                try:
                    from src.agents.analysis.results_analyst import ResultsAnalyst
                    analyst = ResultsAnalyst()
                    st.session_state[run_cache_key] = analyst.explain("full_run", full_data)
                except Exception as e:
                    st.session_state[run_cache_key] = f"Analysis unavailable: {e}"

    if st.session_state[run_cache_key]:
        with st.expander("📋 Run Analysis", expanded=True):
            st.markdown(st.session_state[run_cache_key])


# ── Router ────────────────────────────────────────────────────────────────────

render_run_analysis_button()

_p = st.session_state.page
if   "Overview"     in _p: page_overview()
elif "Performance"  in _p: page_portfolio()
elif "Jury"         in _p: page_jury()
elif "Trade"        in _p: page_trades()
elif "Ablation"     in _p: page_ablation()
elif "Architecture" in _p: page_architecture()
