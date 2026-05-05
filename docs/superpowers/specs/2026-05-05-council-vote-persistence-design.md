# Council Vote Persistence — Design Spec

**Date:** 2026-05-05  
**Scope:** Narrative Trading System — LangGraph agent pipeline  
**Status:** Approved

---

## Problem

The `store.store_council_vote()` method exists in `src/state/store.py` but is never called. As a result, the Agent Council Debates section of the Streamlit dashboard always shows "No council votes in this run" even after a successful full system run.

---

## Goal

Wire the three council agents (Strategist, Contrarian, Synthesizer) to persist their votes to Supabase after each deliberation round, so the dashboard displays real debate data.

---

## Architecture

Three changes, all confined to the graph layer:

```
workflow.py
  └── build_full_graph(store=None)     ← accepts optional DataStore

nodes.py
  ├── make_strategist_node(store)      ← returns closure capturing store
  ├── make_contrarian_node(store)      ← returns closure capturing store
  └── make_synthesizer_node(store)     ← returns closure capturing store
```

The existing top-level node functions (`strategist_node`, `contrarian_node`, `synthesizer_node`) are replaced by factory functions that return closures. Each closure captures the store and calls `store.store_council_vote()` after the agent generates its vote.

The strategy wrapper in `run_ablation.py` passes the store when calling `build_full_graph(store=store)`.

---

## Data Written to Supabase

Each council node writes one record per deliberation round:

| Field | Source |
|-------|--------|
| `run_id` | `state["run_id"]` |
| `agent_name` | `vote["agent_name"]` — `"strategist"`, `"contrarian"`, or `"synthesizer"` |
| `as_of` | `state["as_of"]` |
| `overall_conviction` | `vote["overall_conviction"]` (float 0–1) |
| `views` | `vote["views"]` (list of 11 instrument views, serialized to JSON) |
| `summary` | `vote["summary"]` (agent's investment thesis) |
| `model_used` | `vote["model_used"]` (e.g. `"openai/gpt-4o"`) |
| `round_number` | `state["council_round"]` |

Fields excluded (not in `CouncilVote`): `prompt_hash`, `response_hash`, `latency_ms`.

---

## Data Flow

```
node called by LangGraph
  → agent.generate_vote(...)         # existing, unchanged
  → store.store_council_vote(...)    # new — only if store is not None
  → return updated state             # existing, unchanged
```

Pattern used in each node:

```python
if store:
    try:
        store.store_council_vote(
            run_id=state["run_id"],
            vote={
                "agent_name": vote["agent_name"],
                "as_of": state["as_of"].isoformat(),
                "overall_conviction": vote["overall_conviction"],
                "views": vote["views"],
                "summary": vote["summary"],
                "model_used": vote["model_used"],
            },
            round_number=state["council_round"],
        )
    except Exception as e:
        logger.warning(f"Failed to persist council vote: {e}")
```

---

## Error Handling

- `store_council_vote()` failures are caught, logged as warnings, and do not interrupt the agent run or affect portfolio decisions.
- The `if store:` guard ensures backward compatibility — existing tests and runs that don't pass a store continue to work with zero changes.

---

## Files Changed

| Action | File | Change |
|--------|------|--------|
| Modify | `src/graph/nodes.py` | Replace 3 node functions with factory functions returning closures |
| Modify | `src/graph/workflow.py` | Accept `store=None` in `build_full_graph()`, pass to node factories |
| Modify | `scripts/run_ablation.py` | Pass `store` to `build_full_graph()` in the strategy wrapper |
| Create | `tests/graph/test_council_vote_persistence.py` | 4 tests covering persistence and backward compat |

---

## Testing

File: `tests/graph/test_council_vote_persistence.py`

4 tests, all using mocked agents and store (no real LLM calls, no real DB):

1. Strategist node calls `store_council_vote` with correct fields
2. Contrarian node calls `store_council_vote` with correct fields
3. Synthesizer node calls `store_council_vote` with correct fields
4. When `store=None`, `store_council_vote` is never called (backward compat)

---

## Out of Scope

- Changes to `CouncilVote` schema or agent internals
- Adding `prompt_hash`, `response_hash`, or `latency_ms` to persisted votes
- Changes to the backtest engine or dashboard
