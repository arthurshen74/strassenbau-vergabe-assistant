# EKT Position Calculation Agent (LangGraph)

A cost-calculation agent for German road-construction LV positions.
The LLM classifies, reads documents, and selects methods (Bauweisen);
**every number comes from deterministic formulas over versioned stores**,
with per-parameter provenance.

## Run

Against a real LV position from a project (DB + Elasticsearch + OpenRouter):

```bash
python -m scripts.run_calculator --project <project_uuid> --oz 01.03.0004
```

Offline-ish (canned LLM replies wired to the FSS demo position, no retrieval;
the position still comes from the DB):

```bash
python -m scripts.run_calculator --project <project_uuid> --oz 01.03.0004 --mock
```

The LLM sites run `settings.calculator_model` (default `openai/gpt-5.4`) via
OpenRouter (`OPENROUTER_API_KEY` in `.env`). The run pauses at the HITL
interrupts (classification gate when confidence is low, driver confirmation
for `confirm:` drivers, batched EKT review at the end) and reads your decision
from stdin. Approving the review emits a VHB Formblatt 223-style row —
Zeitansatz plus Lohn / Stoffe / Geräte / Sonstiges je Mengeneinheit (ohne USt),
bucketed deterministically by each cost formula's Kostenart.

## Observability

Every run is traced to Phoenix via OpenTelemetry: graph nodes, the three LLM
calls and the retrieval calls appear as nested spans under the `ekt-calculator`
project. Start it with `docker compose up phoenix` and open
<http://localhost:6006>. `--no-trace` disables tracing for a run.

## Architecture

```
classify ──(confidence gate)──> [hitl_classify?] ──> resolve_drivers
   └─> hitl_confirm_drivers (interrupt iff the registry marks confirm: drivers)
   └─> derive_drivers (cross-op dependencies, e.g. tonnage, computed ONCE)
   └─> plan_operations ──Send × N (parallel)──> cost_operation  (registry interpreter)
   └─> aggregate_etk ──> assess_risk ──> hitl_review (interrupt) ──> route_feedback
```

| File | Role |
|---|---|
| `registry/*.yaml` | The knowledge base: drivers, derived drivers, operations, methods + criteria, requirement rows (goal → formula → param sources). One file per work type. Layer building: `fss_herstellen`, `asphalttragschicht_herstellen`, `bankett_befestigen`, `dsk_herstellen`; surface prep: `planum_herstellen`, `boden_verdichten`, `unterlage_reinigen`, `asphalt_fraesen`, `laengsmarkierung_entfernen`; interlayer/bond: `asphalteinlage_einbauen`, `bitumenemulsion_aufspruehen` |
| `models.py` | Pydantic: registry schema, LLM structured outputs, cost lines + provenance |
| `stores.py` | Deterministic value stores (mocked): material props/prices, interlayer products, BGL rates, performance rates, crews, fleet |
| `formulas.py` | Formula registry: Pydantic input schema + pure function per formula id. **Only origin of numbers.** |
| `llm_calls.py` | The THREE LLM sites with full prompts: classify / resolve drivers / select method |
| `graph.py` | LangGraph wiring: gate, fan-out (`Send`), interpreter, reducers, interrupts, retrieval seam |
| `../../../scripts/run_calculator.py` | CLI harness over real LV positions |

## RAG wiring

`build_graph(retriever, llm)` takes an async `query -> evidence snippets` callable
and the shared `LLMClient` the three judging sites call through (telemetry +
provider-reasoning capture). The CLI binds the retriever to
`RetrievalService.retrieve_context` scoped to the project, with
`CALCULATOR_RETRIEVAL_CONFIG`: PLUS scope, hybrid dense + BM25 fused by RRF,
multi-question expansion, cross-encoder rerank. The three LLM sites query it
before judging:

- **classify** retrieves project context for the position's Kurztext.
- **resolve_drivers** resolves drivers ONE at a time, each its own LLM call, so
  the run reads as a followable chain and later drivers can lean on earlier ones.
  Each driver is resolved from a single evidence block: `lv_text` drivers from the
  position's own text; `plan`/`project`/`judgment` drivers from retrieved context
  ONLY (query = the driver's German `hint:` + Kurztext, e.g. `strip_length_m` →
  "Ausbaulaenge Baubeschreibung ..."); `tool:*` drivers are fetched
  deterministically and never asked of the LLM. A driver's optional `description:`
  carries its decision rule (e.g. when the Ausbaulaenge counts as the full strip
  length) into the prompt and the review UI.
- **select_method** retrieves context per operation (label + Kurztext); the
  snippets land in the prompt's reasoning-notes slot.

With `retriever=None` (mock) the graph runs document-blind; with `llm=None` the
judging sites only work under `--mock`.

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
   Three HITL points per position: the classification gate, the driver
   confirmation (only for drivers the registry marks `confirm: true` — values
   resting on an assumption, e.g. Ausbaulaenge = strip length; the reviewer
   accepts or corrects, corrections get HITL provenance), and the review.
5. **Feedback routing (stubbed).** Numeric corrections → stores; judgment
   corrections + prose rationale → ReasoningNotes retrieved at the judgment
   sites.

## What's mocked / production path

- Stores are dicts → versioned DB tables fed by Nachkalkulation + BGL 2025.
- `duration_by_performance` is a rate lookup → machine-family physics formulas
  slot in as further formula ids without touching the agent.
- ReasoningNote retrieval at the judgment sites currently reuses general
  project retrieval → dedicated note store with feature filters.
- Eval harness: a handful of hand-graded positions scoring classification,
  driver extraction, method choice, and EKT tolerance.
