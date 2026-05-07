# Asset Mapping Agent — Design Spec

**Goal:** Add a dedicated Asset Mapping Agent that sits between the signal gatherers and the council, translating multi-modal signals into explicit per-ticker directional views before the debate begins.

**Architecture:** New gatherer node (`asset_mapper`) inserted after the existing `signal_aggregator` sync point and before `strategist`. Uses Claude Sonnet. Follows the existing signal/gatherer pattern exactly — no breaking changes to other agents.

**Tech Stack:** Python, LangChain Anthropic (`ChatAnthropic`), LangGraph, Pydantic (via existing `Signal` model), PyYAML config.

---

## Pipeline Position

```
[Macro Sentinel]    ──┐
[Market Technician] ──┼──► [signal_aggregator] ──► [asset_mapper] ──► [Strategist]
[Narrative Analyst] ──┤                                                     │
[Sentiment Scout]   ──┘                                               [Contrarian]
                                                                            │
                                                                      [Synthesizer]
```

Previously: `signal_aggregator` → `strategist` (direct).  
After: `signal_aggregator` → `asset_mapper` → `strategist`.

---

## Output Signal Contract

The agent appends one entry to `state["signals"]` with `signal_type="asset_map"`:

```python
{
    "agent_name": "asset_mapper",
    "signal_type": "asset_map",
    "as_of": "<ISO datetime>",
    "confidence": float,          # 0.0–1.0 overall confidence
    "payload": {
        "views": {
            "SPY":     float,     # -1.0 (strong underweight) to +1.0 (strong overweight)
            "QQQ":     float,
            "IWM":     float,
            "EEM":     float,
            "TLT":     float,
            "SHY":     float,
            "GLD":     float,
            "USO":     float,
            "UUP":     float,
            "VIXY":    float,
            "BTC-USD": float,
        },
        "rationale": {
            "<ticker>": "<one sentence>"   # per-ticker reasoning
        },
        "dominant_theme": str,            # e.g. "flight-to-quality amid tariff uncertainty"
        "model_used": str,
        "prompt_hash": str,
        "response_hash": str,
        "latency_ms": int,
    }
}
```

Scores are directional guidance only — the Strategist and council still produce their own independent votes. The asset map is advisory input, not a mandate.

---

## Prompt Design

The agent formats all available signals into a structured context block:

```
MACRO REGIME: {regime}, confidence {regime_confidence:.0%}
MACRO SUMMARY: {macro_summary}

DOMINANT NARRATIVES: {dominant_narratives}
NEWS SENTIMENT: {overall_news_sentiment}

CROWD SENTIMENT: fear_greed={fear_greed_score}/100, overall={overall_crowd_sentiment}

TECHNICAL SIGNALS:
{per-ticker RSI, momentum summary from market_technician payload}

INSTRUMENTS: SPY, QQQ, IWM, EEM, TLT, SHY, GLD, USO, UUP, VIXY, BTC-USD

For each instrument produce a directional score from -1.0 (strong underweight) to
+1.0 (strong overweight) and a one-sentence rationale. Return only valid JSON.
```

System prompt: "You are an asset mapping specialist. You translate macro, narrative, sentiment, and technical signals into explicit per-instrument directional views. Be concise and specific. Return only valid JSON."

---

## Files

| Action | Path |
|--------|------|
| Create | `src/agents/gatherers/asset_mapper.py` |
| Create | `tests/agents/gatherers/test_asset_mapper.py` |
| Modify | `src/graph/nodes.py` — add `asset_mapper_node()` |
| Modify | `src/graph/workflow.py` — rewire `signal_aggregator` → `asset_mapper` → `strategist` |
| Modify | `config/models.yaml` — add `gatherers.asset_mapper` block |
| Modify | `src/agents/council/strategist.py` — read `asset_map` signal in prompt builder |

---

## `asset_mapper.py` — Class Interface

```python
class AssetMapper(BaseAgent):
    INSTRUMENTS = ["SPY", "QQQ", "IWM", "EEM", "TLT", "SHY",
                   "GLD", "USO", "UUP", "VIXY", "BTC-USD"]

    def __init__(self):
        super().__init__("asset_mapper", "gatherers.asset_mapper")

    def map_assets(self, signals: list[dict], as_of: datetime) -> dict:
        """
        Consume all gatherer signals, call Claude, return signal payload dict.
        Returns empty views dict on failure (graceful degradation).
        """
```

---

## `asset_mapper_node()` — Graph Node

```python
def asset_mapper_node(state: dict, store: DataStore = None) -> dict:
    signals = state.get("signals", [])
    as_of   = state.get("as_of")
    if len(signals) < 2:
        return {"signals": []}          # skip if gatherers mostly failed
    mapper  = AssetMapper()
    payload = mapper.map_assets(signals, as_of)
    signal  = Signal(
        agent_name="asset_mapper",
        signal_type="asset_map",
        as_of=as_of,
        confidence=payload.get("confidence", 0.0),
        payload=payload,
    )
    return {"signals": [signal.model_dump()]}
```

---

## Strategist Integration

In `strategist.py`, the prompt builder gains one new block inserted before the existing signals summary:

```python
asset_map = next((s for s in signals if s.get("signal_type") == "asset_map"), None)
if asset_map and asset_map["payload"].get("views"):
    views = asset_map["payload"]["views"]
    theme = asset_map["payload"].get("dominant_theme", "")
    prompt += f"\nPRE-MAPPED ASSET VIEWS (Asset Mapper, for reference):\n"
    prompt += f"Dominant theme: {theme}\n"
    for ticker, score in views.items():
        direction = "overweight" if score > 0.1 else "underweight" if score < -0.1 else "neutral"
        rationale = asset_map["payload"].get("rationale", {}).get(ticker, "")
        prompt += f"  {ticker}: {score:+.2f} ({direction}) — {rationale}\n"
```

---

## Error Handling

| Failure mode | Behaviour |
|---|---|
| Claude API error | Log warning, return `Signal` with `views={}`, `confidence=0` — council runs normally |
| Malformed JSON response | `parse_json_response()` returns `{}` — same fallback |
| Fewer than 2 input signals | Skip LLM call entirely, return empty signal list |
| Missing ticker in response | Fill with `0.0` (neutral) — no crash |

---

## Config Addition (`models.yaml`)

```yaml
gatherers:
  asset_mapper:
    provider: anthropic
    model: claude-sonnet-4-20250514
    temperature: 0
    max_tokens: 2000
```

---

## Testing

`tests/agents/gatherers/test_asset_mapper.py`:

1. **`test_map_assets_returns_all_tickers`** — mock LLM, assert all 11 tickers present in `views`
2. **`test_map_assets_scores_in_range`** — all scores clamped to `[-1.0, 1.0]`
3. **`test_map_assets_graceful_on_bad_json`** — LLM returns garbage → `views == {}`
4. **`test_asset_mapper_node_skips_with_few_signals`** — state with 1 signal → returns `{"signals": []}`
5. **`test_asset_mapper_node_appends_signal`** — 3 signals in → 1 `asset_map` signal appended

---

## Ablation Compatibility

The `build_no_narrative_graph()` and other ablation variants build their graphs by calling `build_full_graph()` internals. Since `asset_mapper_node` is wired into `build_full_graph`, all variants automatically include it. A future `no_asset_map` ablation variant can be added by removing the `asset_mapper` node and directly connecting `signal_aggregator` → `strategist`.
