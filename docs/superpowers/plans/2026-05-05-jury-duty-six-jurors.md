# Jury Duty — Six-Juror Council Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the agent council from 3 to 6 jurors (adding Risk Manager, Quant, Behavioral Skeptic running in parallel after Contrarian), update the Synthesizer to read all 5 votes, and rename the dashboard tab to "Jury Duty".

**Architecture:** The existing sequential Strategist → Contrarian chain is preserved. After Contrarian, three specialist jurors fan out in parallel (each reads signals + strategist_vote + contrarian_vote), then all three fan in to Synthesizer which now arbitrates 5 votes instead of 2. The `council_votes` table already supports any `agent_name`, so no DB changes are needed.

**Tech Stack:** Python, LangGraph (`StateGraph`), Pydantic (`CouncilVote`), Streamlit, psycopg2 (Supabase), OpenAI/Anthropic APIs via `langchain_openai`/`langchain_anthropic`, pytest.

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `src/state/schema.py` | Add 3 new `NotRequired[dict]` fields to `TradingState` |
| Modify | `config/models.yaml` | Add `risk_manager`, `quant`, `behavioral_skeptic` under `council:` |
| Create | `src/prompts/risk_manager.txt` | Risk Manager LLM prompt |
| Create | `src/agents/council/risk_manager.py` | `RiskManager` agent class |
| Create | `src/prompts/quant.txt` | Quant LLM prompt |
| Create | `src/agents/council/quant.py` | `Quant` agent class |
| Create | `src/prompts/behavioral_skeptic.txt` | Behavioral Skeptic LLM prompt |
| Create | `src/agents/council/behavioral_skeptic.py` | `BehavioralSkeptic` agent class |
| Modify | `src/prompts/synthesizer.txt` | Add 3 new vote sections; update task description |
| Modify | `src/agents/council/synthesizer.py` | Accept 5 votes in `generate_vote` signature |
| Modify | `src/graph/nodes.py` | Add 3 singletons + 3 factory functions; update `make_synthesizer_node` |
| Modify | `src/graph/workflow.py` | Rewire `build_full_graph` and `build_no_narrative_graph` with parallel fan-out/in |
| Modify | `app.py` | Rename tab, rename function, update CSS + `agent_cfg`, fix router |
| Create | `tests/graph/test_jury_duty_persistence.py` | 4 tests for new node factories |

---

## Task 1: State schema — add 3 new vote fields

**Files:**
- Modify: `src/state/schema.py:97-99`
- Test: `tests/test_schema_fields.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schema_fields.py
def test_trading_state_has_jury_fields():
    from src.state.schema import TradingState
    hints = TradingState.__annotations__
    assert "risk_manager_vote" in hints
    assert "quant_vote" in hints
    assert "behavioral_skeptic_vote" in hints
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema_fields.py -v`
Expected: FAIL — `AssertionError` (fields not in annotations)

- [ ] **Step 3: Add the 3 new fields to `TradingState`**

Open `src/state/schema.py`. Find the `# Layer 2: Council deliberation` block (around line 96). Replace:

```python
    # Layer 2: Council deliberation
    strategist_vote: NotRequired[dict]
    contrarian_vote: NotRequired[dict]
    synthesizer_decision: NotRequired[dict]
    council_round: int
```

with:

```python
    # Layer 2: Council deliberation
    strategist_vote: NotRequired[dict]
    contrarian_vote: NotRequired[dict]
    risk_manager_vote: NotRequired[dict]
    quant_vote: NotRequired[dict]
    behavioral_skeptic_vote: NotRequired[dict]
    synthesizer_decision: NotRequired[dict]
    council_round: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schema_fields.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/state/schema.py tests/test_schema_fields.py
git commit -m "feat: add risk_manager_vote, quant_vote, behavioral_skeptic_vote to TradingState"
```

---

## Task 2: Config — add 3 new model entries

**Files:**
- Modify: `config/models.yaml`

No test needed — YAML syntax errors surface immediately on import.

- [ ] **Step 1: Add 3 entries under `council:` in `config/models.yaml`**

Open `config/models.yaml`. Find the `synthesizer:` block under `council:`. After it, add:

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

- [ ] **Step 2: Verify YAML parses cleanly**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('config/models.yaml'))"
```
Expected: no output (no error)

- [ ] **Step 3: Commit**

```bash
git add config/models.yaml
git commit -m "feat: add risk_manager, quant, behavioral_skeptic model config"
```

---

## Task 3: Risk Manager agent

**Files:**
- Create: `src/prompts/risk_manager.txt`
- Create: `src/agents/council/risk_manager.py`
- Test: (covered in Task 7)

- [ ] **Step 1: Create the prompt `src/prompts/risk_manager.txt`**

```
You are the Risk Manager in a multi-agent investment council. Your role is to stress-test the proposed positions. Your philosophy: "The downside you ignore is the one that kills you."

## Current Date: {as_of}
## Current Portfolio: {current_portfolio}

## The Strategist's Thesis
{strategist_vote}

## The Contrarian's Challenge
{contrarian_vote}

## Raw Signals

### Macro Signal:
{macro_signal}

### Technical Signal:
{technical_signal}

### Narrative Signal:
{narrative_signal}

### Sentiment Signal:
{sentiment_signal}

{feedback_section}

## Your Task

Evaluate RISK, not return. Assess:
1. **Concentration risk** — are proposed weights too heavy in correlated assets?
2. **Tail risk** — what is the worst-case scenario if the thesis is wrong?
3. **Drawdown exposure** — given current volatility signals, how bad could max drawdown get?
4. **Liquidity risk** — any positions in instruments with thin markets (VIX, small-caps)?

You may agree with positions that are well-sized. Only reduce weights where risk is genuinely elevated.
Your overall_conviction reflects how comfortable you are with the RISK PROFILE, not the return forecast.

## Output Format

Respond with JSON only:

```json
{{
    "overall_conviction": 0.0-1.0,
    "risk_thesis": "2-3 sentence assessment of the overall risk profile",
    "key_risks": ["risk1", "risk2", "risk3"],
    "concentration_warnings": ["any clusters of correlated risk"],
    "views": [
        {{
            "instrument": "SP500",
            "direction": "bullish" | "bearish" | "neutral",
            "conviction": 0.0-1.0,
            "target_weight": -0.25 to 0.25,
            "reasoning": "Risk-adjusted reasoning for this position size"
        }}
    ]
}}
```

Include a view for every instrument in the universe. Weight down anything with elevated tail risk.
```

- [ ] **Step 2: Create `src/agents/council/risk_manager.py`**

```python
"""Risk Manager — tail risk and concentration specialist.

Uses Claude. Stress-tests proposed positions for drawdown exposure,
concentration risk, and tail scenarios.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.agents.base import BaseAgent
from src.state.schema import CouncilVote, InstrumentView
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("agent.risk_manager")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "risk_manager.txt"
UNIVERSE_INSTRUMENTS = [
    "SP500", "NASDAQ100", "RUSSELL2000", "US_10Y", "US_2Y",
    "GOLD", "OIL_WTI", "DXY", "VIX", "MSCI_EM", "BITCOIN",
]


class RiskManager(BaseAgent):
    """Tail risk and concentration specialist."""

    def __init__(self):
        super().__init__("risk_manager", "council.risk_manager")
        self.prompt_template = PROMPT_PATH.read_text()

    def generate_vote(
        self,
        signals: list[dict],
        strategist_vote: dict,
        contrarian_vote: dict,
        current_portfolio: dict[str, float],
        as_of: datetime,
        store: DataStore | None = None,
    ) -> CouncilVote:
        signal_map = self._organize_signals(signals)

        feedback_section = ""
        if store:
            feedback = store.get_recent_feedback("risk_manager", last_n=5)
            if feedback:
                feedback_section = "## Recent Performance Feedback\n"
                for fb in feedback[-3:]:
                    feedback_section += f"- Period {fb['period_end']}: score={fb['score']:.2f}"
                    if fb["note"]:
                        feedback_section += f" — {fb['note']}"
                    feedback_section += "\n"

        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            current_portfolio=json.dumps(current_portfolio, indent=2),
            strategist_vote=json.dumps(strategist_vote, indent=2, default=str),
            contrarian_vote=json.dumps(contrarian_vote, indent=2, default=str),
            macro_signal=json.dumps(signal_map.get("macro", {}), indent=2),
            technical_signal=json.dumps(signal_map.get("technical", {}), indent=2, default=str),
            narrative_signal=json.dumps(signal_map.get("narrative", {}), indent=2),
            sentiment_signal=json.dumps(signal_map.get("sentiment", {}), indent=2),
            feedback_section=feedback_section,
        )

        response = self.call_llm(prompt)
        parsed = self.parse_json_response(response["content"])

        views = []
        for view_data in parsed.get("views", []):
            views.append(InstrumentView(
                instrument=view_data.get("instrument", ""),
                direction=view_data.get("direction", "neutral"),
                conviction=view_data.get("conviction", 0.5),
                target_weight=view_data.get("target_weight", 0.0),
                reasoning=view_data.get("reasoning", ""),
            ))

        viewed_instruments = {v.instrument for v in views}
        for inst in UNIVERSE_INSTRUMENTS:
            if inst not in viewed_instruments:
                views.append(InstrumentView(
                    instrument=inst,
                    direction="neutral",
                    conviction=0.3,
                    target_weight=0.0,
                    reasoning="No elevated risk identified",
                ))

        return CouncilVote(
            agent_name="risk_manager",
            model_used=response["model_used"],
            overall_conviction=parsed.get("overall_conviction", 0.5),
            views=views,
            summary=parsed.get("risk_thesis", ""),
        )

    def _organize_signals(self, signals: list[dict]) -> dict[str, dict]:
        signal_map = {}
        for s in signals:
            signal_type = s.get("signal_type", "unknown")
            signal_map[signal_type] = s.get("payload", {})
        return signal_map
```

- [ ] **Step 3: Verify import works**

Run:
```bash
python3 -c "from src.agents.council.risk_manager import RiskManager; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/prompts/risk_manager.txt src/agents/council/risk_manager.py
git commit -m "feat: add Risk Manager agent"
```

---

## Task 4: Quant agent

**Files:**
- Create: `src/prompts/quant.txt`
- Create: `src/agents/council/quant.py`
- Test: (covered in Task 7)

- [ ] **Step 1: Create the prompt `src/prompts/quant.txt`**

```
You are the Quant in a multi-agent investment council. Your philosophy: "If it's not in the data, it doesn't exist."

## Current Date: {as_of}
## Current Portfolio: {current_portfolio}

## The Strategist's Thesis (for reference only — you are not bound by it)
{strategist_vote}

## The Contrarian's Challenge (for reference only)
{contrarian_vote}

## Signals

### Technical Signal (your primary input):
{technical_signal}

### Macro Signal (secondary):
{macro_signal}

### Narrative Signal (you are skeptical of this — mention it only if it strongly confirms a technical signal):
{narrative_signal}

### Sentiment Signal (use only as a mean-reversion indicator):
{sentiment_signal}

{feedback_section}

## Your Task

Ignore narratives. Ignore stories. React only to:
1. **Momentum** — which instruments are trending? Use the technical signal's momentum scores.
2. **Mean reversion** — which instruments are stretched beyond normal ranges?
3. **Relative strength** — which assets are outperforming their universe?
4. **Volatility regime** — is volatility expanding (reduce) or contracting (increase)?

Do not explain macro reasoning. Cite signal values directly.

## Output Format

Respond with JSON only:

```json
{{
    "overall_conviction": 0.0-1.0,
    "quant_thesis": "2-3 sentence systematic view based purely on signals",
    "momentum_leaders": ["top momentum instruments"],
    "mean_reversion_candidates": ["stretched instruments likely to revert"],
    "views": [
        {{
            "instrument": "SP500",
            "direction": "bullish" | "bearish" | "neutral",
            "conviction": 0.0-1.0,
            "target_weight": -0.25 to 0.25,
            "reasoning": "Signal value(s) that drive this position"
        }}
    ]
}}
```

Include a view for every instrument in the universe.
```

- [ ] **Step 2: Create `src/agents/council/quant.py`**

```python
"""Quant — pure signal-driven council member.

Uses GPT-4o-mini. Ignores narrative entirely. Trades only on
technical signals, momentum, and mean-reversion.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.agents.base import BaseAgent
from src.state.schema import CouncilVote, InstrumentView
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("agent.quant")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "quant.txt"
UNIVERSE_INSTRUMENTS = [
    "SP500", "NASDAQ100", "RUSSELL2000", "US_10Y", "US_2Y",
    "GOLD", "OIL_WTI", "DXY", "VIX", "MSCI_EM", "BITCOIN",
]


class Quant(BaseAgent):
    """Pure signal-driven, systematic council member."""

    def __init__(self):
        super().__init__("quant", "council.quant")
        self.prompt_template = PROMPT_PATH.read_text()

    def generate_vote(
        self,
        signals: list[dict],
        strategist_vote: dict,
        contrarian_vote: dict,
        current_portfolio: dict[str, float],
        as_of: datetime,
        store: DataStore | None = None,
    ) -> CouncilVote:
        signal_map = self._organize_signals(signals)

        feedback_section = ""
        if store:
            feedback = store.get_recent_feedback("quant", last_n=5)
            if feedback:
                feedback_section = "## Recent Performance Feedback\n"
                for fb in feedback[-3:]:
                    feedback_section += f"- Period {fb['period_end']}: score={fb['score']:.2f}"
                    if fb["note"]:
                        feedback_section += f" — {fb['note']}"
                    feedback_section += "\n"

        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            current_portfolio=json.dumps(current_portfolio, indent=2),
            strategist_vote=json.dumps(strategist_vote, indent=2, default=str),
            contrarian_vote=json.dumps(contrarian_vote, indent=2, default=str),
            macro_signal=json.dumps(signal_map.get("macro", {}), indent=2),
            technical_signal=json.dumps(signal_map.get("technical", {}), indent=2, default=str),
            narrative_signal=json.dumps(signal_map.get("narrative", {}), indent=2),
            sentiment_signal=json.dumps(signal_map.get("sentiment", {}), indent=2),
            feedback_section=feedback_section,
        )

        response = self.call_llm(prompt)
        parsed = self.parse_json_response(response["content"])

        views = []
        for view_data in parsed.get("views", []):
            views.append(InstrumentView(
                instrument=view_data.get("instrument", ""),
                direction=view_data.get("direction", "neutral"),
                conviction=view_data.get("conviction", 0.5),
                target_weight=view_data.get("target_weight", 0.0),
                reasoning=view_data.get("reasoning", ""),
            ))

        viewed_instruments = {v.instrument for v in views}
        for inst in UNIVERSE_INSTRUMENTS:
            if inst not in viewed_instruments:
                views.append(InstrumentView(
                    instrument=inst,
                    direction="neutral",
                    conviction=0.3,
                    target_weight=0.0,
                    reasoning="No signal",
                ))

        return CouncilVote(
            agent_name="quant",
            model_used=response["model_used"],
            overall_conviction=parsed.get("overall_conviction", 0.5),
            views=views,
            summary=parsed.get("quant_thesis", ""),
        )

    def _organize_signals(self, signals: list[dict]) -> dict[str, dict]:
        signal_map = {}
        for s in signals:
            signal_type = s.get("signal_type", "unknown")
            signal_map[signal_type] = s.get("payload", {})
        return signal_map
```

- [ ] **Step 3: Verify import works**

Run:
```bash
python3 -c "from src.agents.council.quant import Quant; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/prompts/quant.txt src/agents/council/quant.py
git commit -m "feat: add Quant agent"
```

---

## Task 5: Behavioral Skeptic agent

**Files:**
- Create: `src/prompts/behavioral_skeptic.txt`
- Create: `src/agents/council/behavioral_skeptic.py`
- Test: (covered in Task 7)

- [ ] **Step 1: Create the prompt `src/prompts/behavioral_skeptic.txt`**

```
You are the Behavioral Skeptic in a multi-agent investment council. Your philosophy: "When everyone agrees, someone is wrong — and it's probably the crowd."

## Current Date: {as_of}
## Current Portfolio: {current_portfolio}

## The Strategist's Thesis
{strategist_vote}

## The Contrarian's Challenge
{contrarian_vote}

## Raw Signals

### Sentiment Signal (your primary input):
{sentiment_signal}

### Narrative Signal (look for consensus narratives):
{narrative_signal}

### Technical Signal:
{technical_signal}

### Macro Signal:
{macro_signal}

{feedback_section}

## Your Task

Challenge assumptions rooted in crowd behavior and sentiment:
1. **Positioning extremes** — is the crowd already max-long or max-short on any asset? That's a reversal signal.
2. **Consensus narratives** — if both the Strategist and Contrarian agree, ask: is this trade too crowded?
3. **Fear/greed extremes** — is the market too euphoric (sell signal) or too fearful (buy signal)?
4. **Recency bias** — are agents over-weighting recent performance and ignoring base rates?
5. **Narrative-price divergence** — where is the story bullish but price has already moved?

You are not a pure contrarian — you may agree with positions where sentiment is not stretched.

## Output Format

Respond with JSON only:

```json
{{
    "overall_conviction": 0.0-1.0,
    "behavioral_thesis": "2-3 sentence assessment of market psychology and crowd positioning",
    "crowded_trades": ["instruments where positioning is extreme"],
    "sentiment_extremes": {{"instrument": "fear | greed | neutral"}},
    "views": [
        {{
            "instrument": "SP500",
            "direction": "bullish" | "bearish" | "neutral",
            "conviction": 0.0-1.0,
            "target_weight": -0.25 to 0.25,
            "reasoning": "Behavioral/sentiment reasoning for this position"
        }}
    ]
}}
```

Include a view for every instrument in the universe.
```

- [ ] **Step 2: Create `src/agents/council/behavioral_skeptic.py`**

```python
"""Behavioral Skeptic — crowd psychology and sentiment analyst.

Uses GPT-4o. Challenges positions driven by consensus narratives,
extreme sentiment, and crowded trades.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.agents.base import BaseAgent
from src.state.schema import CouncilVote, InstrumentView
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("agent.behavioral_skeptic")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "behavioral_skeptic.txt"
UNIVERSE_INSTRUMENTS = [
    "SP500", "NASDAQ100", "RUSSELL2000", "US_10Y", "US_2Y",
    "GOLD", "OIL_WTI", "DXY", "VIX", "MSCI_EM", "BITCOIN",
]


class BehavioralSkeptic(BaseAgent):
    """Crowd psychology and sentiment challenge specialist."""

    def __init__(self):
        super().__init__("behavioral_skeptic", "council.behavioral_skeptic")
        self.prompt_template = PROMPT_PATH.read_text()

    def generate_vote(
        self,
        signals: list[dict],
        strategist_vote: dict,
        contrarian_vote: dict,
        current_portfolio: dict[str, float],
        as_of: datetime,
        store: DataStore | None = None,
    ) -> CouncilVote:
        signal_map = self._organize_signals(signals)

        feedback_section = ""
        if store:
            feedback = store.get_recent_feedback("behavioral_skeptic", last_n=5)
            if feedback:
                feedback_section = "## Recent Performance Feedback\n"
                for fb in feedback[-3:]:
                    feedback_section += f"- Period {fb['period_end']}: score={fb['score']:.2f}"
                    if fb["note"]:
                        feedback_section += f" — {fb['note']}"
                    feedback_section += "\n"

        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            current_portfolio=json.dumps(current_portfolio, indent=2),
            strategist_vote=json.dumps(strategist_vote, indent=2, default=str),
            contrarian_vote=json.dumps(contrarian_vote, indent=2, default=str),
            macro_signal=json.dumps(signal_map.get("macro", {}), indent=2),
            technical_signal=json.dumps(signal_map.get("technical", {}), indent=2, default=str),
            narrative_signal=json.dumps(signal_map.get("narrative", {}), indent=2),
            sentiment_signal=json.dumps(signal_map.get("sentiment", {}), indent=2),
            feedback_section=feedback_section,
        )

        response = self.call_llm(prompt)
        parsed = self.parse_json_response(response["content"])

        views = []
        for view_data in parsed.get("views", []):
            views.append(InstrumentView(
                instrument=view_data.get("instrument", ""),
                direction=view_data.get("direction", "neutral"),
                conviction=view_data.get("conviction", 0.5),
                target_weight=view_data.get("target_weight", 0.0),
                reasoning=view_data.get("reasoning", ""),
            ))

        viewed_instruments = {v.instrument for v in views}
        for inst in UNIVERSE_INSTRUMENTS:
            if inst not in viewed_instruments:
                views.append(InstrumentView(
                    instrument=inst,
                    direction="neutral",
                    conviction=0.3,
                    target_weight=0.0,
                    reasoning="No behavioral signal",
                ))

        return CouncilVote(
            agent_name="behavioral_skeptic",
            model_used=response["model_used"],
            overall_conviction=parsed.get("overall_conviction", 0.5),
            views=views,
            summary=parsed.get("behavioral_thesis", ""),
        )

    def _organize_signals(self, signals: list[dict]) -> dict[str, dict]:
        signal_map = {}
        for s in signals:
            signal_type = s.get("signal_type", "unknown")
            signal_map[signal_type] = s.get("payload", {})
        return signal_map
```

- [ ] **Step 3: Verify import works**

Run:
```bash
python3 -c "from src.agents.council.behavioral_skeptic import BehavioralSkeptic; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/prompts/behavioral_skeptic.txt src/agents/council/behavioral_skeptic.py
git commit -m "feat: add Behavioral Skeptic agent"
```

---

## Task 6: Update Synthesizer to accept all 5 votes

**Files:**
- Modify: `src/prompts/synthesizer.txt`
- Modify: `src/agents/council/synthesizer.py:47-72`

- [ ] **Step 1: Replace `src/prompts/synthesizer.txt` entirely**

```
You are the Synthesizer — the final decision maker in a six-juror investment council. Your job is to weigh five independent perspectives and produce the final portfolio decision. Your philosophy: "Find the actionable intersection, reject the noise."

## Current Date: {as_of}
## Current Portfolio: {current_portfolio}
## Debate Round: {round_number} of {max_rounds}

## The Strategist's View (macro-first thesis)
{strategist_vote}

## The Contrarian's View (devil's advocate)
{contrarian_vote}

## The Risk Manager's View (tail risk and concentration)
{risk_manager_vote}

## The Quant's View (pure signal, no narrative)
{quant_vote}

## The Behavioral Skeptic's View (crowd positioning and sentiment)
{behavioral_skeptic_vote}

## Your Task

1. Identify where the majority of jurors AGREE — these are highest-conviction positions
2. Where jurors DISAGREE, weigh the strength of each argument
3. Give extra weight to Risk Manager warnings — asymmetric downside matters more than upside
4. Treat the Quant as a tiebreaker when narrative-based jurors conflict
5. Produce final target weights that reflect the consensus across all five

Your overall conviction score determines next steps:
- >= 0.6: Decision is executed (proceed to portfolio construction)
- < 0.6: Another debate round occurs (Strategist and Contrarian re-argue)

## Output Format

Respond with JSON only:

```json
{{
    "overall_conviction": 0.0-1.0,
    "synthesis": "3-4 sentence explanation of your decision process",
    "agreement_areas": ["instruments where the majority agreed"],
    "resolution_notes": {{
        "INSTRUMENT_NAME": "How you resolved disagreement among jurors"
    }},
    "views": [
        {{
            "instrument": "SP500",
            "direction": "bullish" | "bearish" | "neutral",
            "conviction": 0.0-1.0,
            "target_weight": -0.25 to 0.25,
            "reasoning": "Final reasoning incorporating all five views"
        }}
    ],
    "final_thesis": "One sentence summary of the portfolio thesis"
}}
```

Include a view for every instrument in the universe. Target weights must be between -0.25 and 0.25 per instrument. All positive weights should sum to no more than 0.95 (leaving room for cash).
```

- [ ] **Step 2: Update `generate_vote` signature in `src/agents/council/synthesizer.py`**

Replace the `generate_vote` method (starting at line ~47) with:

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
        """Synthesize all five jurors' views into a final decision."""
        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            current_portfolio=json.dumps(current_portfolio, indent=2),
            strategist_vote=json.dumps(strategist_vote, indent=2, default=str),
            contrarian_vote=json.dumps(contrarian_vote, indent=2, default=str),
            risk_manager_vote=json.dumps(risk_manager_vote, indent=2, default=str),
            quant_vote=json.dumps(quant_vote, indent=2, default=str),
            behavioral_skeptic_vote=json.dumps(behavioral_skeptic_vote, indent=2, default=str),
            round_number=round_number,
            max_rounds=self.max_rounds,
        )

        response = self.call_llm(prompt)
        parsed = self.parse_json_response(response["content"])

        views = []
        for view_data in parsed.get("views", []):
            views.append(InstrumentView(
                instrument=view_data.get("instrument", ""),
                direction=view_data.get("direction", "neutral"),
                conviction=view_data.get("conviction", 0.5),
                target_weight=view_data.get("target_weight", 0.0),
                reasoning=view_data.get("reasoning", ""),
            ))

        viewed_instruments = {v.instrument for v in views}
        for inst in UNIVERSE_INSTRUMENTS:
            if inst not in viewed_instruments:
                views.append(InstrumentView(
                    instrument=inst,
                    direction="neutral",
                    conviction=0.3,
                    target_weight=0.0,
                    reasoning="No consensus view",
                ))

        total_positive = sum(v.target_weight for v in views if v.target_weight > 0)
        if total_positive > 0.95:
            scale = 0.95 / total_positive
            for v in views:
                if v.target_weight > 0:
                    v.target_weight = round(v.target_weight * scale, 4)

        return CouncilVote(
            agent_name="synthesizer",
            model_used=response["model_used"],
            overall_conviction=parsed.get("overall_conviction", 0.5),
            views=views,
            summary=parsed.get("synthesis", parsed.get("final_thesis", "")),
        )
```

- [ ] **Step 3: Verify import works**

Run:
```bash
python3 -c "from src.agents.council.synthesizer import Synthesizer; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/prompts/synthesizer.txt src/agents/council/synthesizer.py
git commit -m "feat: update Synthesizer to accept all 5 jury votes"
```

---

## Task 7: Node factories for the 3 new jurors + update synthesizer node

**Files:**
- Modify: `src/graph/nodes.py`
- Create: `tests/graph/test_jury_duty_persistence.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/graph/test_jury_duty_persistence.py`:

```python
"""Tests for jury duty (new juror) vote persistence.

All agents and DataStore are mocked — no real LLM calls or DB connections.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

AS_OF = datetime(2026, 3, 15, 12, 0, 0)

SPECIALIST_STATE = {
    "run_id": "test-run-001",
    "as_of": AS_OF,
    "signals": [],
    "current_portfolio": {},
    "council_round": 1,
    "strategist_vote": {"agent_name": "strategist"},
    "contrarian_vote": {"agent_name": "contrarian"},
}

SYNTHESIZER_STATE = {
    "run_id": "test-run-001",
    "as_of": AS_OF,
    "signals": [],
    "current_portfolio": {},
    "council_round": 1,
    "strategist_vote": {"agent_name": "strategist"},
    "contrarian_vote": {"agent_name": "contrarian"},
    "risk_manager_vote": {"agent_name": "risk_manager"},
    "quant_vote": {"agent_name": "quant"},
    "behavioral_skeptic_vote": {"agent_name": "behavioral_skeptic"},
}


def _make_fake_vote(agent_name: str, conviction: float = 0.65) -> MagicMock:
    vote = MagicMock()
    vote.agent_name = agent_name
    vote.overall_conviction = conviction
    vote.views = []
    vote.summary = f"{agent_name} summary."
    vote.model_used = "openai/gpt-4o"
    vote.model_dump.return_value = {
        "agent_name": agent_name,
        "overall_conviction": conviction,
        "views": [],
        "summary": f"{agent_name} summary.",
        "model_used": "openai/gpt-4o",
    }
    return vote


def test_risk_manager_node_calls_store_council_vote():
    from src.graph.nodes import make_risk_manager_node

    mock_store = MagicMock()
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = _make_fake_vote("risk_manager")

    with patch("src.graph.nodes._get_risk_manager", return_value=mock_agent):
        node = make_risk_manager_node(mock_store)
        node(SPECIALIST_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args
    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "risk_manager"
    assert vote_arg["as_of"] == AS_OF.isoformat()


def test_quant_node_calls_store_council_vote():
    from src.graph.nodes import make_quant_node

    mock_store = MagicMock()
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = _make_fake_vote("quant")

    with patch("src.graph.nodes._get_quant", return_value=mock_agent):
        node = make_quant_node(mock_store)
        node(SPECIALIST_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args
    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "quant"
    assert vote_arg["as_of"] == AS_OF.isoformat()


def test_behavioral_skeptic_node_calls_store_council_vote():
    from src.graph.nodes import make_behavioral_skeptic_node

    mock_store = MagicMock()
    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = _make_fake_vote("behavioral_skeptic")

    with patch("src.graph.nodes._get_behavioral_skeptic", return_value=mock_agent):
        node = make_behavioral_skeptic_node(mock_store)
        node(SPECIALIST_STATE)

    mock_store.store_council_vote.assert_called_once()
    call_kwargs = mock_store.store_council_vote.call_args
    assert call_kwargs.kwargs["run_id"] == "test-run-001"
    assert call_kwargs.kwargs["round_number"] == 1
    vote_arg = call_kwargs.kwargs["vote"]
    assert vote_arg["agent_name"] == "behavioral_skeptic"
    assert vote_arg["as_of"] == AS_OF.isoformat()


def test_new_nodes_skip_persistence_when_store_is_none():
    from src.graph.nodes import make_risk_manager_node, make_quant_node, make_behavioral_skeptic_node

    mock_agent = MagicMock()
    mock_agent.generate_vote.return_value = _make_fake_vote("risk_manager")

    with patch("src.graph.nodes._get_risk_manager", return_value=mock_agent):
        node = make_risk_manager_node(None)
        result = node(SPECIALIST_STATE)

    # If the 'if store is not None:' guard is absent, calling None.store_council_vote()
    # would raise AttributeError here, causing the test to fail.
    assert "risk_manager_vote" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/graph/test_jury_duty_persistence.py -v`
Expected: FAIL — `ImportError: cannot import name 'make_risk_manager_node'`

- [ ] **Step 3: Add singletons and 3 new factory functions to `src/graph/nodes.py`**

At the top of the file, add 3 new imports after the existing council imports (line ~13):

```python
from src.agents.council.risk_manager import RiskManager
from src.agents.council.quant import Quant
from src.agents.council.behavioral_skeptic import BehavioralSkeptic
```

After the existing `_synthesizer = None` singleton (line ~27), add:

```python
_risk_manager = None
_quant = None
_behavioral_skeptic = None
```

After the existing `_get_synthesizer()` function (line ~55), add:

```python
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
```

After the existing `make_contrarian_node` function, add the 3 new factory functions:

```python
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
        agent = _get_risk_manager()
        vote = agent.generate_vote(
            signals, strategist_vote, contrarian_vote, current_portfolio, as_of
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
        agent = _get_quant()
        vote = agent.generate_vote(
            signals, strategist_vote, contrarian_vote, current_portfolio, as_of
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
        agent = _get_behavioral_skeptic()
        vote = agent.generate_vote(
            signals, strategist_vote, contrarian_vote, current_portfolio, as_of
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
```

- [ ] **Step 4: Update `make_synthesizer_node` to pass all 5 votes**

In `make_synthesizer_node`, find the `vote = agent.generate_vote(...)` call and replace it with:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/graph/test_jury_duty_persistence.py -v`
Expected: 4 PASS

- [ ] **Step 6: Run existing persistence tests to ensure nothing broke**

Run: `pytest tests/graph/test_council_vote_persistence.py -v`
Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add src/graph/nodes.py tests/graph/test_jury_duty_persistence.py
git commit -m "feat: add Risk Manager, Quant, Behavioral Skeptic node factories; update Synthesizer node"
```

---

## Task 8: Rewire the LangGraph workflow

**Files:**
- Modify: `src/graph/workflow.py`

- [ ] **Step 1: Add new imports to `src/graph/workflow.py`**

Find the existing import block at the top of `src/graph/workflow.py`:

```python
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
```

Replace it with:

```python
from src.graph.nodes import (
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
```

- [ ] **Step 2: Update `build_full_graph` — add nodes and rewire edges**

In `build_full_graph`, find the `# Layer 2: Council debate nodes` block:

```python
    # Layer 2: Council debate nodes
    builder.add_node("strategist", make_strategist_node(store))
    builder.add_node("contrarian", make_contrarian_node(store))
    builder.add_node("synthesizer", make_synthesizer_node(store))
```

Replace with:

```python
    # Layer 2: Council debate nodes
    builder.add_node("strategist", make_strategist_node(store))
    builder.add_node("contrarian", make_contrarian_node(store))
    builder.add_node("risk_manager", make_risk_manager_node(store))
    builder.add_node("quant", make_quant_node(store))
    builder.add_node("behavioral_skeptic", make_behavioral_skeptic_node(store))
    builder.add_node("synthesizer", make_synthesizer_node(store))
```

Find the council debate edges:

```python
    # Edges: aggregator -> council debate (sequential)
    builder.add_edge("signal_aggregator", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "synthesizer")
```

Replace with:

```python
    # Edges: aggregator -> council debate
    builder.add_edge("signal_aggregator", "strategist")
    builder.add_edge("strategist", "contrarian")
    # Fan-out: contrarian -> 3 specialist jurors in parallel
    builder.add_edge("contrarian", "risk_manager")
    builder.add_edge("contrarian", "quant")
    builder.add_edge("contrarian", "behavioral_skeptic")
    # Fan-in: all 3 specialists must complete before Synthesizer runs
    builder.add_edge("risk_manager", "synthesizer")
    builder.add_edge("quant", "synthesizer")
    builder.add_edge("behavioral_skeptic", "synthesizer")
```

- [ ] **Step 3: Update `build_no_narrative_graph` with the same changes**

Find the nodes block in `build_no_narrative_graph`:

```python
    builder.add_node("strategist", make_strategist_node(store))
    builder.add_node("contrarian", make_contrarian_node(store))
    builder.add_node("synthesizer", make_synthesizer_node(store))
```

Replace with:

```python
    builder.add_node("strategist", make_strategist_node(store))
    builder.add_node("contrarian", make_contrarian_node(store))
    builder.add_node("risk_manager", make_risk_manager_node(store))
    builder.add_node("quant", make_quant_node(store))
    builder.add_node("behavioral_skeptic", make_behavioral_skeptic_node(store))
    builder.add_node("synthesizer", make_synthesizer_node(store))
```

Find the edges block in `build_no_narrative_graph`:

```python
    builder.add_edge("signal_aggregator", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "synthesizer")
```

Replace with:

```python
    builder.add_edge("signal_aggregator", "strategist")
    builder.add_edge("strategist", "contrarian")
    builder.add_edge("contrarian", "risk_manager")
    builder.add_edge("contrarian", "quant")
    builder.add_edge("contrarian", "behavioral_skeptic")
    builder.add_edge("risk_manager", "synthesizer")
    builder.add_edge("quant", "synthesizer")
    builder.add_edge("behavioral_skeptic", "synthesizer")
```

- [ ] **Step 4: Verify both graphs compile without errors**

Run:
```bash
python3 -c "
from src.graph.workflow import build_full_graph, build_no_narrative_graph
from src.state.store import DataStore
g1 = build_full_graph()
g2 = build_no_narrative_graph()
print('both graphs compiled OK')
"
```
Expected: `both graphs compiled OK`

- [ ] **Step 5: Commit**

```bash
git add src/graph/workflow.py
git commit -m "feat: rewire graph — parallel fan-out to Risk Manager, Quant, Behavioral Skeptic after Contrarian"
```

---

## Task 9: Dashboard — rename tab and add new juror cards

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Rename the tab in `NAV_OPTIONS`**

Find (around line 355):
```python
    "⚖️  Agent Council",
```
Replace with:
```python
    "⚖️  Jury Duty",
```

- [ ] **Step 2: Add 3 new CSS badge styles**

Find (around line 192):
```python
.badge-strategist  { background: #dbeafe; color: #1d4ed8; }
.badge-contrarian  { background: #fce7f3; color: #9d174d; }
.badge-synthesizer { background: #d1fae5; color: #065f46; }
```
Replace with:
```python
.badge-strategist  { background: #dbeafe; color: #1d4ed8; }
.badge-contrarian  { background: #fce7f3; color: #9d174d; }
.badge-synthesizer { background: #d1fae5; color: #065f46; }
.badge-risk        { background: #fee2e2; color: #991b1b; }
.badge-quant       { background: #fef9c3; color: #854d0e; }
.badge-skeptic     { background: #ede9fe; color: #5b21b6; }
```

- [ ] **Step 3: Rename `page_council` to `page_jury` and update heading**

Find:
```python
# ── Page: Agent Council ───────────────────────────────────────────────────────

def page_council():
    st.markdown("<h2 style='color:#0f172a;font-weight:800;margin-bottom:1.5rem;'>Agent Council Debates</h2>",
```
Replace with:
```python
# ── Page: Jury Duty ───────────────────────────────────────────────────────────

def page_jury():
    st.markdown("<h2 style='color:#0f172a;font-weight:800;margin-bottom:1.5rem;'>Jury Duty</h2>",
```

- [ ] **Step 4: Update `agent_cfg` and juror count**

Find:
```python
    agent_cfg = {
        "strategist":  ("🎯", "Strategist",  "badge-strategist",  "Proposes investment thesis based on all signals"),
        "contrarian":  ("⚡", "Contrarian",  "badge-contrarian",  "Challenges the thesis — finds crowded trades and missed risks"),
        "synthesizer": ("⚖️", "Synthesizer", "badge-synthesizer", "Mediates and produces the final portfolio decision"),
    }
```
Replace with:
```python
    agent_cfg = {
        "strategist":         ("🎯", "Strategist",         "badge-strategist", "Proposes investment thesis based on all signals"),
        "contrarian":         ("⚡", "Contrarian",         "badge-contrarian",  "Challenges the thesis — finds crowded trades and missed risks"),
        "risk_manager":       ("🛡️", "Risk Manager",       "badge-risk",        "Stress-tests tail risk and concentration"),
        "quant":              ("📐", "Quant",              "badge-quant",       "Pure signal-driven, ignores narrative"),
        "behavioral_skeptic": ("🧠", "Behavioral Skeptic", "badge-skeptic",     "Challenges crowd positioning and sentiment consensus"),
        "synthesizer":        ("⚖️", "Synthesizer",        "badge-synthesizer", "Mediates and produces the final portfolio decision"),
    }
```

Find:
```python
            metric_card("Agents", f"{len(date_votes)} / 3 voted")
```
Replace with:
```python
            metric_card("Agents", f"{len(date_votes)} / 6 voted")
```

- [ ] **Step 5: Update the router**

Find (near the bottom of `app.py`):
```python
elif "Council"      in _p: page_council()
```
Replace with:
```python
elif "Jury"         in _p: page_jury()
```

- [ ] **Step 6: Verify Streamlit reloads cleanly**

The Streamlit server auto-reloads on file save. Open http://localhost:8503 and confirm:
- Sidebar shows "⚖️  Jury Duty" instead of "⚖️  Agent Council"
- Navigating to Jury Duty shows the heading "Jury Duty"
- Existing vote cards still render (Strategist, Contrarian, Synthesizer) with correct badges
- No Python traceback in the terminal

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "feat: rename Agent Council tab to Jury Duty; add Risk Manager, Quant, Behavioral Skeptic cards"
```
