# Project Context — Implementation Status

Status of implementing `PROJECT_CONTEXT_PLAN.md` (project-scoped "global" context
variables in the EKT position-calculation flow). Builds on, and refactors, the
`lieferanten-wahl` branch.

- **Branch:** `lieferanten-wahl` (off `main`)
- **State:** all 7 plan phases implemented; **uncommitted**. Pure-engine changes verified by
  direct execution; the persistence/resolver/API/graph/UI layers **compile** (`py_compile`) but
  were **not run** in the build sandbox (no `uv`/`pytest`/`sqlalchemy`/`langgraph`, no populated
  `ui/node_modules`/`json2ts`). See [Verification](#verification).
- **Scope:** 22 files modified, 14 new (see [File inventory](#file-inventory)).

---

## What the feature does

A small set of variables are **project-wide** (the whole Vergabe / road section), not
per-position: where the **Baustelle** is, where spoil goes (**Deponie**), the section
**dimensions** (length × width), and the **Fräsgutklasse**. They are resolved **once per
project** (RAG → synthesis → user confirmation), **persisted with per-variable version
history** (SCD-2), and **reused by every LV calculation**.

A new **pre-Gate-A stage** in the calculator graph resolves, reconciles (against values the
estimator already stated in chat), and presents them for **Confirm / Override / resolve-Conflict**
before the per-position flow. The confirmed Baustelle drives supplier ranking; the routed
Baustelle→Deponie distance fills `entfernung_deponie_km`; the strip dims are a geometry
**fallback**; the Fräsgutklasse is a per-position default (still surfaced at Gate B).

Precedence (§3): **per-position input > project global > catalog KONSTANTE default**.

---

## Phase 1 — versioned persistence, SCD-2 (verified by model validation)

| Area | Change |
|------|--------|
| `db/tables/project_context_values.py` **(new)** | One row per `(project, variable, version)`. SCD-2 columns (`ist_aktuell`, `gueltig_ab`, `gueltig_bis`), provenance (`quelle`, `beleg`, `quelle_referenz` JSONB, `konfidenz`, `benutzer`, `status`), `UNIQUE(project,variable,version)` + a partial unique index `uq_pcv_aktuell` (one current row per variable). |
| `models/enums.py` | New `ContextQuelle` (rag/hitl/routing) and `ContextStatus` (aufgeloest/unsicher/fehlgeschlagen) discriminators. |
| `models/project_context.py` **(new)** | `ProjectContextValue` (one version) + `NewProjectContextValue` (insert shape). |
| `repositories/project_context_values.py` **(new)** | `current` / `history` / `as_of` (point-in-time) projections + `supersede` (close out the current row, insert `version+1`; never mutate a prior version). |
| `db/tables/__init__.py`, `db/unit_of_work.py` | Register the table + `uow.project_context_values`. |

The table is created by `metadata.create_all` (bootstrap), no Alembic.

## Phase 2 — resolver (verified offline via mock fixtures in the repo tests)

| Area | Change |
|------|--------|
| `services/kalkulation_v2/globale_variablen.py` **(new)** | `GlobaleVariable` registry: `baustelle_location`, `deponie_location` (`ist_standort`), `strip_length_m` (→ `laenge_m`), `strip_width_m`, `fraesgut_klasse` (→ `fraesgut_klasse`). Variable-name + engine-target (`ZIEL_*`) constants. `entfernung_deponie_km` is a derived governed variable (not a registry member). |
| `services/project_context/llm.py` **(new)** | `resolve_globale` — the dedicated `PROJECT_CONTEXT_RESOLVE` structured synthesis over the hybrid-RAG chunks, **one variable per call** (`{wert, konfidenz, beleg}` + reasoning). |
| `services/project_context/service.py` **(new)** | `ProjectContextService(conn)`: `resolve` (retrieve→synthesize→geocode→supersede RAG, then route the deponie distance), `save` (override → HITL versions, re-geocode locations, recompute distance), `current_read` / `history`. Mock mode uses fixtures + the mock geocoder. Holds the `DEFAULT_USER` placeholder. |
| `services/project_context/prompts.py` **(new)** | `load_resolve_prompt` — loads `PROJECT_CONTEXT_RESOLVE` **independently** of `load_calculator_prompts` (an unseeded prompt must not break per-position calc). |
| `models/enums.py` | `PromptType.PROJECT_CONTEXT_RESOLVE`. |
| `scripts/seed/prompts/project_context_resolve.prompt` **(new)** | The synthesis prompt (German, one-variable, structured). Seed with `python -m scripts.seed.prompts`. |

## Phase 3 — API + optional panel

| Area | Change |
|------|--------|
| `models/project_context_schema.py` **(new)** | `ProjectContextRead` (flat current view), `ProjectContextUpdate` (editable subset), `ProjectContextHistory` (governance). |
| `api/routes/project_contexts.py` **(new)** | `GET /context`, `GET /context/history`, `PUT /context`, `POST /context/resolve`. Registered in `api/main.py`. |
| `scripts/export_schema.py` | Exports the four DTOs (incl. nested `ProjectContextValue`). **Run `npm run gen:types`** (see Verification). |
| `ui/src/api/project-context.ts` **(new)** | `useProjectContext`, `useProjectContextHistory`, `useUpdateProjectContext`, `useResolveProjectContext`. |
| `ui/src/views/main/ProjectContextPanel.tsx` **(new)** | A "Context" tab on `ProjectDetails`: view/resolve/override the globals + version history. |

## Phase 4 — graph integration

New topology (`services/calculator/graph.py`):

```
launch -> extract_chat_values (also harvests global candidates)
  -> load_project_context (resolve/reconcile via injected loader)
  -> project_context_review (pre-Gate-A interrupt: Confirm/Override/Conflict; saves via injected saver)
  -> classify_leistung -> rank_lieferanten (split from locate_baustelle; uses confirmed project coords)
  -> method_review (Gate A; per-position Baustelle field removed)
  -> bind_resources -> bind_lieferant (reuses the project-coord ranking; no re-geocode)
  -> derive_required_variables -> resolve_variables (merges project globals as proposals)
  -> variable_review (Gate B) -> compute -> render_output
```

- **DB/retrieval stay out of the graph:** `build_graph` gains `project_context_loader` /
  `project_context_saver` async callables (the `retriever`-callable idiom). `run_service` injects
  closures that open short transactions and call `ProjectContextService.resolve` / `.save`
  (`benutzer = DEFAULT_USER`). With neither seam wired (standalone tests), the gate is a no-op and
  any pre-seeded `projekt_kontext` is used.
- **Injection:** `resolve_variables` merges the project globals (`_projekt_werte`) into the existing
  `gebundene_werte` proposal merge — so each becomes a Gate-B-overridable proposal that flows to
  `compute` via the confirmed `werte`. High-stakes globals (Fräsgutklasse) stay **surfaced**.
- **Geometry (§9):** strip dims source `laenge_m` / `flaeche_m2` **only** as a fallback — they apply
  solely to a leaf still on the worklist; a booked geometry is pruned, so provided geometry always wins.
- **State:** per-position `baustelle_*` fields replaced by `projekt_kontext` + `projekt_kontext_reconcile`
  + `chat_global_kandidaten`. `STAGE_PROJECT_CONTEXT_REVIEW` + `RECONCILE_*` constants added.
- **UI:** `InterruptPanel` gets a `ProjectContextReview` component (Confirm/Override/Conflict, status
  badges); the per-position Baustelle field is removed from `MethodReview`. `CalculationResume` gains
  `projekt_kontext` and drops `baustelle`.

## Phase 5 — geometry + ranker

| Area | Change |
|------|--------|
| `services/calculator/lieferant_ranking.py` | `rang_lieferanten` now returns `LieferantenRangliste(angebote, warnung)`. A **soft radius filter** (`calculator_lieferant_radius_km`, default 100) drops far carriers before routing; **no-carrier-in-radius → single nearest + a WARNING**. Road distance scaled by `calculator_hgv_detour_factor` (default 1.0). |
| `shared/config.py` | `calculator_lieferant_radius_km`, `calculator_hgv_detour_factor`. |
| graph | `rank_lieferanten` emits the no-radius warning into `warnungen` + the reasoning log. Geometry fallback wired as above. |

## Phase 6 — reasoning UX

`AssistantMessage` gains a `collapsible` mode: the calculator's streaming reasoning collapses to
its **latest line** with an **expand toggle** (full history kept), and a prominent **"Berechnung
läuft…" spinner** while streaming. Threaded `MessageList → Message → AssistantMessage`, gated by a
new `isCalculating` flag from `useWorkspaceConversation` (true during HITL-**resume** segments, which
are always calculator reasoning — so a normal chat answer is never mislabeled).

## Phase 7 — cleanup

- Removed `locate_baustelle`, per-position `baustelle_*` state, the Gate-A Baustelle field +
  override, and the `koordinate()` Baustelle vars from `kontext_variablen.py` (verified no engine refs).
- `entfernung_deponie_km` keeps its 10 km KONSTANTE last-resort fallback; `fraesgut_klasse` keeps its
  per-position definition (now also fed by the project default).
- This document.

---

## Decisions / deviations from the plan

- **`fraesgut_klasse` chat statements stay per-position.** It is both a project global *and* a
  per-position engine variable. A chat statement about it is a per-position input (precedence §3), so
  it is **not** reconciled as a project candidate (only true non-engine globals — locations, strip
  dims — are). The project-global Fräsgutklasse is set via RAG / the review / the panel. This also
  preserves the existing `test_live_chat_value_pins_source_zero` behavior.
- **`bind_lieferant` reuses the `rank_lieferanten` ranking** instead of re-geocoding/re-routing —
  the Baustelle coords are project-level and fixed for the run, so a second routing call is redundant.
- **Reasoning collapse is scoped to the streaming resume segment** (the verbose per-variable
  resolution). Persisted reasoning from earlier segments stays expanded as the transcript/audit.
- **`ContextQuelle` / `ContextStatus` live in `models/enums.py`** (the codebase's single source of
  truth for discriminators), not inline in `models/project_context.py` as the plan sketched.

---

## Verification

Run in a full environment:

```bash
uv sync && uv run pytest        # repo (SCD-2), resolver (mock), graph (mock), ranker, API
# Existing DB only: widen the prompt_type CHECK for the new prompt (create_all won't alter it).
psql -d roadbuilders -f sql/09_project_context_prompt_types.sql
docker compose up -d            # then seed the new prompt:
docker compose exec -T api python -m scripts.seed.prompts
npm --prefix ui run gen:types   # regenerate ui/src/types/generated.ts (adds ProjectContext* DTOs)
npm --prefix ui run build       # typecheck + bundle the UI
```

`project_context_values` (the new table) is created by `metadata.create_all` on boot — no DDL
script needed. The only schema migration for an existing DB is the prompt_type CHECK widening above.

**Done in the sandbox:**
- All touched Python files pass `python -m py_compile`.
- The pure `kalkulation_v2` engine assembles cleanly: the catalog builds without the removed
  per-position Baustelle vars, `entfernung_deponie_km` / `fraesgut_klasse` retained, the strip
  targets (`laenge_m` / `flaeche_m2`) exist, and the FRAESEN worklist still has the expected leaves.
- The new Pydantic models + the global registry validate.

**NOT done in the sandbox (must run in the full env):**
- `uv run pytest` — the repo/resolver/graph/ranker/API tests (no `sqlalchemy`/`langgraph`/`pytest`).
- `npm run gen:types` — needs the docker `api` service + `json2ts`. **Until it runs, the new UI files
  (`project-context.ts`, `ProjectContextPanel.tsx`) won't typecheck** (the `ProjectContext*` types are
  not yet in `generated.ts`). `npm run build` will fail until then.
- Seeding `PROJECT_CONTEXT_RESOLVE` and any live LLM/geocoding/routing path.

---

## Tests added

- `tests/integration/repositories/test_project_context_values.py` — SCD-2 supersede/current/history/as_of.
- `tests/integration/services/test_project_context_service.py` — resolve (mock fixtures), save (HITL
  versions + reroute), idempotent resolve, numeric-only save does not reroute.
- `tests/unit/services/test_project_context_resolver.py` — `_quelle_referenz` provenance shape, `resolve_globale` wiring.
- `tests/integration/api/test_project_context_api.py` — GET/resolve/PUT/history lifecycle + 404.
- `tests/unit/services/test_calculator_graph.py` — new project-context review gate test (override flows
  into the calc); supplier tests reseeded with `projekt_kontext` coords; removed the obsolete Gate-A
  Baustelle test.
- `tests/unit/services/test_lieferant_ranking.py` — result-object return, radius nearest-fallback + WARNING, HGV factor.

## Deferred (unchanged from the plan §18)

- True HGV/truck routing (the detour factor is a stopgap; Google can't truck-route).
- Eager resolution at project creation/ingestion (currently lazy on first calc).
- Multi-section projects (one context stream per project assumes one Baustelle/section).
- Real `benutzer` once fastapi-users lands (thread the authenticated user into `save`, replacing `DEFAULT_USER`).
