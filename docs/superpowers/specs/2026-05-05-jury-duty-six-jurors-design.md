# Jury Duty — Six-Juror Council Design

## Goal

Expand the agent council from 3 members (Strategist, Contrarian, Synthesizer) to 6 (adding Risk Manager, Quant, Behavioral Skeptic), and rename the dashboard tab to "Jury Duty".

## Architecture

The debate pipeline stays sequential for the first two jurors (Strategist sets the thesis, Contrarian challenges it), then fans out in parallel to three specialist jurors, then fans back into the Synthesizer who reads all five votes.

```
signal_aggregator
       ↓
  Strategist              ← sets macro thesis
       ↓
  Contrarian              ← challenges thesis
    ↓     ↓     ↓         ← parallel fan-out
Risk Mgr  Quant  Behavioral Skeptic
    ↓     ↓     ↓         ← fan-in (all 3 complete before Synthesizer runs)
       Synthesizer         ← reads all 5 votes, produces final decision
       ↓
  portfolio_constructor
       ↓
  order_manager
```

Each of the 3 new jurors receives: signals + strategist_vote + contrarian_vote. They do not see each other's votes.

## New Agents

### Risk Manager (`src/agents/council/risk_manager.py`)
- **Role:** Assesses concentration risk, tail risk, max drawdown exposure. Votes to reduce or cap position sizes when risk-adjusted metrics are elevated. Focuses on what can go wrong, not what the expected return is.
- **Model:** `claude-sonnet-4-20250514` (Anthropic) via `council.risk_manager` config key
- **Prompt:** `src/prompts/risk_manager.txt`
- **`generate_vote` signature:** `(signals, strategist_vote, contrarian_vote, current_portfolio, as_of, store=None) -> CouncilVote`
- **`agent_name`:** `"risk_manager"`

### Quant (`src/agents/council/quant.py`)
- **Role:** Ignores narrative and sentiment entirely. Reads only technical signals (momentum, mean-reversion, trend). Cold and systematic — if the signal isn't in the data, it doesn't exist.
- **Model:** `gpt-4o-mini` (OpenAI) via `council.quant` config key
- **Prompt:** `src/prompts/quant.txt`
- **`generate_vote` signature:** `(signals, strategist_vote, contrarian_vote, current_portfolio, as_of, store=None) -> CouncilVote`
- **`agent_name`:** `"quant"`

### Behavioral Skeptic (`src/agents/council/behavioral_skeptic.py`)
- **Role:** Challenges sentiment signals. Flags crowded trades, euphoria, panic, and consensus narratives. Asks: is everyone already positioned this way? If so, where's the counter-trade?
- **Model:** `gpt-4o` (OpenAI) via `council.behavioral_skeptic` config key
- **Prompt:** `src/prompts/behavioral_skeptic.txt`
- **`generate_vote` signature:** `(signals, strategist_vote, contrarian_vote, current_portfolio, as_of, store=None) -> CouncilVote`
- **`agent_name`:** `"behavioral_skeptic"`

## State Schema Changes (`src/state/schema.py`)

Add three optional fields to `TradingState`:
```python
risk_manager_vote: dict = field(default_factory=dict)
quant_vote: dict = field(default_factory=dict)
behavioral_skeptic_vote: dict = field(default_factory=dict)
```

## Graph Changes (`src/graph/workflow.py`)

### `build_full_graph` and `build_no_narrative_graph`

Add 3 new nodes after Contrarian, wired in parallel:
```python
builder.add_node("risk_manager", make_risk_manager_node(store))
builder.add_node("quant", make_quant_node(store))
builder.add_node("behavioral_skeptic", make_behavioral_skeptic_node(store))

# Fan-out from contrarian
builder.add_edge("contrarian", "risk_manager")
builder.add_edge("contrarian", "quant")
builder.add_edge("contrarian", "behavioral_skeptic")

# Fan-in to synthesizer
builder.add_edge("risk_manager", "synthesizer")
builder.add_edge("quant", "synthesizer")
builder.add_edge("behavioral_skeptic", "synthesizer")
```

Remove the direct `contrarian → synthesizer` edge that currently exists.

## Nodes Changes (`src/graph/nodes.py`)

Add three factory functions following the existing pattern:
- `make_risk_manager_node(store=None)` → reads `strategist_vote` and `contrarian_vote` from state
- `make_quant_node(store=None)` → reads `strategist_vote` and `contrarian_vote` from state
- `make_behavioral_skeptic_node(store=None)` → reads `strategist_vote` and `contrarian_vote` from state

Each returns its vote as `{"risk_manager_vote": vote_data}` (or `quant_vote`, `behavioral_skeptic_vote`) and persists via `store.store_council_vote(...)` if store is not None.

## Synthesizer Changes (`src/agents/council/synthesizer.py`)

Update `generate_vote` signature to accept the two new votes:
```python
def generate_vote(
    self,
    strategist_vote: dict,
    contrarian_vote: dict,
    risk_manager_vote: dict,
    quant_vote: dict,
    behavioral_skeptic_vote: dict,
    current_portfolio: dict[str, float],
    as_of: datetime,
    round_number: int = 1,
) -> CouncilVote:
```

Update `src/prompts/synthesizer.txt` to include all five votes in the prompt template.

## Config Changes (`config/models.yaml`)

Add under the `council:` section:
```yaml
  risk_manager:
    provider: anthropic
    model: claude-sonnet-4-20250514
    temperature: 0
    max_tokens: 3000

  quant:
    provider: openai
    model: gpt-4o-mini
    temperature: 0
    max_tokens: 3000

  behavioral_skeptic:
    provider: openai
    model: gpt-4o
    temperature: 0
    max_tokens: 3000
```

## Dashboard Changes (`app.py`)

- `NAV_OPTIONS`: `"⚖️  Agent Council"` → `"⚖️  Jury Duty"`
- `page_council()` → `page_jury()`, heading text → "Jury Duty"
- `agent_cfg` extended:
  ```python
  "risk_manager":       ("🛡️", "Risk Manager",         "badge-risk",     "Stress-tests tail risk and concentration"),
  "quant":              ("📐", "Quant",                 "badge-quant",    "Pure signal-driven, ignores narrative"),
  "behavioral_skeptic": ("🧠", "Behavioral Skeptic",   "badge-skeptic",  "Challenges crowd positioning and sentiment consensus"),
  ```
- CSS: add `.badge-risk`, `.badge-quant`, `.badge-skeptic` styles (follow existing badge pattern)
- Router at bottom of app.py: add `elif page == "⚖️  Jury Duty": page_jury()`; remove old `Agent Council` route

## Database

No schema changes. The `council_votes` table already stores any agent by `agent_name`. The 3 new agents write rows with `agent_name` in `{"risk_manager", "quant", "behavioral_skeptic"}`.

## Testing

New test file: `tests/graph/test_jury_duty_persistence.py`
- `test_risk_manager_node_calls_store_council_vote`
- `test_quant_node_calls_store_council_vote`
- `test_behavioral_skeptic_node_calls_store_council_vote`
- `test_new_nodes_skip_persistence_when_store_is_none`

Follow the exact pattern in `tests/graph/test_council_vote_persistence.py`.
