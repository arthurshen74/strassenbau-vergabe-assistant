# EKT Position Calculation Agent (LangGraph)

A cost-calculation (Einzelkosten der Teilleistung) agent for German road-construction LV
positions. The LLM only **classifies and reads** — which Leistung the position is, which values
the Kalkulator stated in chat, which value the Langtext implies. **Every number comes from the
deterministic `kalkulation_v2` engine** — a Decimal formula cascade over a versioned catalog +
master data — with per-variable provenance. Two human-in-the-loop gates bracket the run.

## Run

Against a real LV position from a project (DB + Elasticsearch + OpenRouter):

```bash
python -m scripts.run_calculator --project <project_uuid> --oz 01.02.0006
```

Offline mock (canned LLM replies + pinned inputs, no retrieval):

```bash
python -m scripts.run_calculator --project <project_uuid> --oz 01.02.0006 \
    --mock --leistung L_FRAESEN_3_45 --set tiefe_cm=4 --set fraesgut_klasse=1
```

The LLM sites run `settings.calculator_model` (default `openai/gpt-5.4`) via OpenRouter
(`OPENROUTER_API_KEY` in `.env`). The run pauses at the two HITL interrupts — **Gate A** (confirm
the Leistung, pick the Bauverfahren + machine/Baustoff) and **Gate B** (review the resolved
variables) — and reads your decision. The result is an **EKT row** (Einheits- + Gesamtpreis with a
cost line per Kostenart), a **Nachweistabelle** (every resolved variable: value, unit, provenance),
and a short narration. In the UI the same run streams over SSE and resumes across the gates
(`run_service.py`).

## Observability

Every run is traced to Phoenix via OpenTelemetry: graph nodes, the LLM calls and the retrieval
calls appear as nested spans under the `ekt-calculator` project. Start it with
`docker compose up phoenix` and open <http://localhost:6006>. `--no-trace` disables tracing.

## Architecture

The calculator is a thin HITL + LLM orchestration around the deterministic **kalkulation_v2**
engine (`../kalkulation_v2/`, see its `ARCHITECTURE.md`). The engine owns the catalog
(Leistung → Bauverfahren → Vorgang → Ausführungsart), the variable-resolution cascade
(LANGTEXT / RAG / HITL / STAMMDATEN / FORMEL / KONSTANTE), and the Decimal `Kalkulator`; the graph
decides *what to ask a human or the LLM* and feeds the answers back in.

```
launch → extract_chat_values → classify_leistung
  → method_review        (Gate A interrupt: confirm Leistung, pick Bauverfahren + machine/Baustoff)
  → bind_resources       (right-size a machine per slot; attach the matched Baustoff)
  → derive_required_variables   (walk the recipe's formula tree → worklist leaves)
  → resolve_variables    (propose value + provenance + review tier per leaf)
  → variable_review      (Gate B interrupt: tiered accept/override)
  → compute              (deterministic engine run → EKT row + Nachweistabelle)
  → render_output        (narration)
```

| File | Role |
|---|---|
| `graph.py` | The StateGraph: nodes, the two HITL interrupts, machine/Baustoff resolution, reducers, the retrieval seam |
| `state.py` | State envelope (plain-JSON for the Postgres checkpointer) + output artifacts (EKTZeile, Nachweistabelle) |
| `llm_calls.py` | The LLM sites with structured Pydantic outputs: `classify_leistung`, `extract_chat_values`, `extract_value` (Langtext/RAG), `narrate_output` |
| `prompts.py` | Loads the four DB-backed prompt versions; raises if a required prompt is not seeded |
| `run_service.py` | Worker/SSE harness: runs the graph as a conversation, streams reasoning, resumes across the gates |
| `../kalkulation_v2/` | The deterministic engine: catalog, master data, formulas, `Kalkulator`, machine fleet, Baustoff BM25 |
| `../../../scripts/run_calculator.py` | CLI harness over real LV positions |

## Resource selection (machine + material)

`bind_resources` fills the slots the chosen recipe needs:

- **Machine** — candidates come from the fleet by `Ausführungsart`; the default is **right-sized**
  (`maschinen_sortiert`: the smallest machine whose capacity clears the job within
  `settings.calculator_maschine_zielstunden`). The Kalkulator overrides per slot in Gate A. A bound
  machine's rates + productivity flow into the calc and surface (overridable) in Gate B.
- **Material** — only for recipes that consume a graded Baustoff. A hand-rolled **BM25** matcher
  (`baustoff_suche`) grounds the LV Langtext (normed TL SoB-StB / TL Asphalt-StB designation) to a
  catalog code; a separation confidence ≥ `settings.calculator_baustoff_match_threshold` auto-applies,
  otherwise the top hit is surfaced for confirmation in Gate A. The matcher can only ever return a
  cataloged code — no hallucinated material.

## RAG wiring

`build_graph(retriever, llm)` takes an async `query → snippets` callable and the shared `LLMClient`
(telemetry + provider-reasoning capture). The CLI binds the retriever to the project-scoped
`RetrievalService` (PLUS scope, hybrid dense + BM25 fused by RRF, multi-question expansion,
cross-encoder rerank). `classify_leistung` and the Langtext/RAG variable extraction query it before
judging. With `retriever=None` the graph runs document-blind; `settings.calculator_mock` swaps every
LLM site for canned replies (and `extract_chat_values` reads the `--set` pins instead).

## Design decisions

1. **Determinism guardrail.** The LLM writes only judgment (which Leistung, which values are
   stated). Every euro is an engine formula output over the catalog + master data; each resolved
   variable carries provenance (LANGTEXT / RAG / HITL / STAMMDATEN / KONSTANTE). The golden L101
   fixture pins the engine total.
2. **Two gates, not many.** Gate A fixes the method + resources before the worklist is derived;
   Gate B reviews every leaf, tiered — high-stakes inputs surfaced, rates/master-data collapsed but
   overridable. No interrupts inside the deterministic compute.
3. **Selection is grounded, not hallucinated.** Machine and material are chosen from the catalog
   (fleet candidacy + right-sizing; BM25 over the Baustoff catalog) and confirmed by HITL — never
   free-generated by the LLM.
4. **Engine-owned worklist.** `derive_required_variables` walks the chosen recipe to its leaves, so
   the graph topology stays position-agnostic; adding a Leistung/recipe needs no graph change.

## What's mocked / production path

- The catalog (Leistungen, recipes, fleet, Baustoffe) and master-data rates are plausible prototype
  values in `kalkulation_v2/`; the names use real norm designations, so classification + BM25
  matching behave realistically. They become versioned DB tables fed by Nachkalkulation + BGL.
- Machine mob/demob (`mobilisierung_eur` / `demobilisierung_eur`) is in the property bags but no
  cost line consumes it yet — wiring it would let cost-optimal right-sizing emerge.
- The four prompts are DB-backed (`prompt_versions`); seed with `python -m scripts.seed.prompts`.
