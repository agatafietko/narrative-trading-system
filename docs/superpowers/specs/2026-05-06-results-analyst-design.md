# Results Analyst Agent — Design Spec

## Goal

Add an on-demand AI analyst to the Streamlit dashboard that explains charts, jury verdicts, and ablation results in plain English — targeted at users who need to interpret complex outputs without deep quant knowledge.

## Architecture

The `ResultsAnalyst` is a standalone Claude Sonnet agent called directly from the dashboard on button click. It is **not** part of the LangGraph workflow — no changes to the graph, state schema, or backtest engine.

**Files:**
- `src/agents/analysis/__init__.py` — new package
- `src/agents/analysis/results_analyst.py` — agent class
- `src/prompts/results_analyst.txt` — prompt template

**Two call modes:**
- **Section mode** — receives a context type (`jury_duty`, `performance`, `ablation`) and the relevant data slice. Returns 3–5 plain-English sentences focused on that section.
- **Full run mode** — receives all run data combined. Returns a structured 4-section report.

## Agent Behaviour

**Model:** Claude Sonnet (hardcoded — not swappable in ablations)

**Prompt instructions:**
- Use plain English, no jargon unless it already appears on screen
- Reference actual numbers from the data (real conviction scores, real returns, real instrument names)
- Section explanations: 3–5 sentences
- Full run report: 4 sections × 2–3 sentences each
  - **Verdict** — what the jury decided and why consensus was or wasn't reached
  - **Portfolio Changes** — what was bought/sold and the reasoning
  - **Key Risks** — what the Risk Manager and Behavioral Skeptic flagged
  - **Watch List** — what to monitor before the next rebalance
- No financial disclaimer hedging

## Dashboard Changes

### "Explain this" buttons (per section)

| Tab | Button label | Context passed |
|-----|-------------|----------------|
| Jury Duty | "Explain this jury verdict" | All 6 juror cards (conviction, thesis, views) |
| Performance | "Explain this performance" | NAV, return, Sharpe, Sortino, max drawdown, baseline comparison |
| Ablation | "Explain these results" | Full ablation comparison table |

Each button:
- Shows `st.spinner("Analyzing...")` while waiting
- Renders result in `st.info()` box below the button
- Caches result in `st.session_state` keyed by run ID + section — clicking twice does not re-call the API

### "Analyze this run" button (full report)

- Positioned at the top of the main content area, visible on all tabs
- Triggers full run mode with all available data for the selected run
- Result renders as a `st.expander("Run Analysis", expanded=True)` panel with 4 labelled sections
- Also cached in `st.session_state` by run ID

## Data Flow

```
User clicks button
       |
       v
app.py collects relevant state (votes, metrics, weights)
       |
       v
ResultsAnalyst.explain(mode, data) called
       |
       v
Prompt built from results_analyst.txt template
       |
       v
Claude Sonnet API call (Anthropic SDK)
       |
       v
Plain-text response rendered in dashboard
```

## Error Handling

- If the API call fails, show `st.warning("Analysis unavailable — check API key")` instead of crashing
- If no data is available for a section (e.g. no council votes), button is disabled with `st.button(..., disabled=True)`

## What Is Not Changing

- LangGraph graph structure
- State schema
- Backtest engine
- Supabase schema
- Any existing agent
