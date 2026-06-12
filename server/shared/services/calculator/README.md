# EKT Position Calculation Agent (LangGraph)

A cost-calculation agent for German road-construction LV positions.
The LLM classifies, reads documents, and selects methods (Bauweisen);
**every number comes from deterministic formulas over versioned stores**,
with per-parameter provenance. Course project, Part 3 (LLM Agents).

## Run

```bash
pip install -r requirements.txt
python main.py                    # offline demo (EKT_MOCK=1, canned LLM replies)
EKT_MOCK=0 ANTHROPIC_API_KEY=... python main.py   # live LLM via LangChain
```

The demo runs the real tender position **L101 / OZ 01.03.0004** (Frostschutz-
schicht in the Verbreiterungsstreifen) end-to-end, pauses at the HITL review
interrupt, prints the EKT + batched review flags, then resumes with "approve".

## Architecture

```
classify ──(confidence gate)──> [hitl_classify?] ──> resolve_drivers
   └─> derive_drivers (cross-op dependencies, e.g. tonnage, computed ONCE)
   └─> plan_operations ──Send × N (parallel)──> cost_operation  (registry interpreter)
   └─> aggregate_etk ──> assess_risk ──> hitl_review (interrupt) ──> route_feedback
```

| File | Role |
|---|---|
| `registry/fss_herstellen.yaml` | The knowledge base: drivers, derived drivers, operations, methods + criteria, requirement rows (goal → formula → param sources) |
| `models.py` | Pydantic: registry schema, LLM structured outputs, cost lines + provenance |
| `stores.py` | Deterministic value stores (mocked): material props/prices, BGL rates, performance rates, crews, fleet |
| `formulas.py` | Formula registry: Pydantic input schema + pure function per formula id. **Only origin of numbers.** |
| `llm_calls.py` | The THREE LLM sites with full prompts: classify / resolve drivers / select method |
| `graph.py` | LangGraph wiring: gate, fan-out (`Send`), interpreter, reducers, interrupts |
| `main.py` | Demo on the real position |

## Design decisions (the writeup skeleton)

1. **Determinism guardrail.** The LLM writes only judgment fields (work_type,
   driver decisions, method). Numbers exist only as formula outputs over store
   reads; each `CostLine` parameter carries provenance (`driver:` / `store:` /
   `prior:` / `const`). Provenance is enforced by control flow, not trust.
2. **Registry as program.** The YAML is walked by an interpreter; the agent
   executes rows instead of browsing a tool catalog. Decision criteria are
   data, so a Kalkulator can change selection logic in a reviewed PR.
   The registry version is pinned into the EKT for reproducibility.
3. **Cross-operation dependencies as derived drivers.** `prior:` refs are only
   legal within an operation; shared quantities (tonnage) are computed once in
   `derive_drivers`, keeping every `Send` branch independent and parallel.
4. **Optimistic execution, batched review.** No interrupts inside the fan-out:
   low-confidence judgments and blocked rows append `review_flags`
   (reducer-merged) and surface at the single `hitl_review` interrupt.
   Only two HITL points per position: the classification gate and the review.
5. **Feedback routing (stubbed).** Numeric corrections → stores; judgment
   corrections + prose rationale → ReasoningNotes retrieved at the judgment
   sites (`get_hitl_reasoning`, to be wired to the Part 2 RAG).

## What's mocked / production path

- Stores are dicts → versioned DB tables fed by Nachkalkulation + BGL 2025.
- `duration_by_performance` is a rate lookup → machine-family physics formulas
  slot in as further formula ids without touching the agent.
- `resolve_drivers` context is pasted excerpts → Part 2 RAG retrieval.
- ReasoningNote retrieval at the judgment sites is passed empty → hybrid
  BM25/semantic store with feature filters.
- Eval harness: a handful of hand-graded positions scoring classification,
  driver extraction, method choice, and EKT tolerance.
