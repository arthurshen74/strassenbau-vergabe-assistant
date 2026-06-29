# Lieferantenwahl — Implementation Status

Status of implementing `LIEFERANTENWAHL_PLAN.md` (supplier selection in the EKT
position-calculation StateGraph).

- **Branch:** `lieferanten-wahl` (off `main`)
- **State:** both slices implemented; **uncommitted**. Pure-engine changes verified by
  direct execution; the graph/maps/ranker/UI layers compile but were **not run** in the
  build sandbox (see [Verification](#verification)).
- **Scope:** 13 files changed, 4 new (see [File inventory](#file-inventory)).

---

## What the feature does

For each position with a material, the estimator picks a **Lieferant** at **Gate A**
(cheapest-delivered pre-selected, overridable). The chosen supplier drives **two existing,
separate cost inputs** (so no double-counting — Material and Antransport were already
distinct cost lines):

1. the **ex-works material price** replaces the Baustoff catalog base price, and
2. the **supplier→Baustelle road distance** fills the inbound Antransport distance.

The Baustelle location is geocoded from the Baubeschreibung; supplier road distances come
from the Google Routes API. The deterministic calc engine stays I/O-free — geocoding and
routing happen in graph nodes that fill resolved values before `compute`.

---

## Slice 1 — engine / data foundation (verified by direct execution)

| Area | Change |
|------|--------|
| `kalkulation_v2/store.py` | Calls `lade_preise(BAUSTOFFE, LIEFERANTEN)` at catalog assembly (was only called in `__main__`). 515 price rows now attach to `LIEFERANTEN[*].preise` at startup. |
| `kalkulation_v2/kontext_variablen.py` | New `koordinate()` helper + required `baustelle_breitengrad` / `baustelle_laengengrad` (cascade RAG→HITL, **no** KONSTANTE default). Split the shared `entfernung_km` into `entfernung_lieferant_km` (Antransport) and `entfernung_deponie_km` (Abtransport); both keep a 10 km HITL default. Old `entfernung_km` removed. |
| `kalkulation_v2/formel.py` | Rewired the 5 `trans_*` lines: `trans_material` / `trans_asphalt` → `entfernung_lieferant_km`; `trans_boden` / `trans_fraesgut` / `trans_aufbruch` → `entfernung_deponie_km`. |
| `kalkulation_v2/positionen.py` | Renamed the pinned `entfernung_km` in 13 fixtures **by the direction each recipe actually uses** (traced via Vorgänge → `trans_*`): disposal positions `01.00.0002`, `01.03.0001`, `01.03.0007` → `entfernung_deponie_km`; the 10 supply positions → `entfernung_lieferant_km`. |
| `shared/config.py` | Added `google_maps_geocoding_url`, `google_maps_route_matrix_url`, `maps_request_timeout_seconds`. Reuses the existing `google_static_maps_api_key` (same Google Maps Platform key). |
| `shared/clients/maps/geo.py` **(new)** | `geocode()` (Geocoding API), `route_matrix()` / `road_distance_km()` (Routes API `computeRouteMatrix`), `GeocodeResult`, `Koordinate`, `MapsError`. Mock mode (`settings.calculator_mock`) returns a fixed fixture coordinate (`51.42, 10.81`) and haversine×1.3 distances — no network. Live `route_matrix` falls back to haversine **per origin/destination pair** when Google has no route. |
| `shared/clients/maps/__init__.py` | Exports the new geo symbols. |
| `services/calculator/lieferant_ranking.py` **(new)** | Async `rang_lieferanten()` → `LieferantAngebot` (code, name, ort, werk €/t, road km, frei-Bau €/t), sorted cheapest-delivered. Pre-filters to the N nearest carriers by haversine, then route-matrixes only those. `materialien.guenstigster_lieferant` (sync/haversine) is kept as the offline baseline. |

---

## Slice 2 — graph + UI (compiled; not run)

### Topology

```
launch → extract_chat_values → classify_leistung
  → locate_baustelle      (NEW)
  → method_review         (Gate A: + per-material supplier picker)
  → bind_resources
  → bind_lieferant        (NEW)
  → derive_required_variables → resolve_variables
  → variable_review       (Gate B)
  → compute → render_output
```

### `services/calculator/graph.py`

- **`locate_baustelle` node** — geocodes the site (mock: fixture coord; live: RAG snippet →
  `geocode`) and ranks suppliers for the proposed Baustoff into `lieferanten_vorschlag`.
  **Skips entirely when the position has no material** (no supplier needed), which keeps
  material-free positions — and the live fräsen tests — off the network. Low-confidence
  live geocodes raise a warning surfaced at Gate A.
- **`bind_lieferant` node** — finalizes the supplier: honours the Gate A pick **iff** that
  supplier carries the final Baustoff, else auto-picks cheapest-delivered (mirror of the
  machine-pick fallback). Stashes `lieferant_werkspreis` (price override), `lieferant_beleg`
  (audit), and `lieferant_werte` (the `entfernung_lieferant_km` resolved value).
- **Gate A (`method_review`)** — payload gains `lieferanten_vorschlag` (keyed by
  `baustoff_code`); answer gains `lieferanten` (`baustoff_code → lieferant_code`).
- **`resolve_variables`** — merges the supplier distance into the Gate B proposal (collapsed,
  overridable) alongside machine rates, and uses an effective (price-overridden) Baustoff so
  the STAMMDATEN price-bridge proposals show the supplier price.
- **`compute`** — applies the override via `_effektiver_baustoff` (a single
  `model_copy(basispreis_eur / basispreis_eur_pro_t = werk)` that flows through every
  STAMMDATEN price bridge), injects the supplier distance, and `_nachweis` re-labels whichever
  price bridge the recipe used with the supplier beleg.
- Helpers: `_effektiver_baustoff()`; `_stammdaten_wert()` / `_catalog_vorschlag()` now take a
  `Baustoff`; `_nachweis()` takes an optional `preis_beleg`. Constants:
  `LIEFERANT_DISTANCE_VAR`, `GEOCODE_HITL_THRESHOLD`, `STAMMDATEN_PREIS_PRAEFIX`.

### `services/calculator/state.py`

Added (all JSON-serializable for the Postgres checkpointer): `baustelle_breitengrad`,
`baustelle_laengengrad`, `lieferanten_vorschlag`, `gewaehlter_lieferant`, `lieferant_code`,
`lieferant_werkspreis`, `lieferant_beleg`, `lieferant_werte`.

### `services/calculator/run_service.py`

**No change needed.** The Gate A `lieferanten` pick flows through the normal `Command(resume=…)`
into `method_review`; `_capture_gate_b` early-returns for Gate A (no overrides / ground-truth).

### UI

- `ui/src/views/workspace/InterruptPanel.tsx` — per-material supplier `<select>` in Gate A
  (default = cheapest, shows "name (ort) — frei-Bau €/t · Werk · km"); switching material
  switches the supplier list. Resume sends `lieferanten: { [baustoff]: lieferant }`. Coded to
  the existing `?? []` pattern to stay safe under `noUncheckedIndexedAccess`.
- `ui/src/api/calculations.ts` — `CalculationResume` gained `lieferanten?: Record<string,string>`.
- **No `gen:types` needed** — the interrupt payload and resume decision are passed as untyped
  dicts, not OpenAPI/`generated.ts` types.

---

## Key design decisions

- **Supplier drives both inputs, no double-count.** Material and Antransport are already
  separate cost lines; the supplier feeds the ex-works price and the inbound distance
  independently.
- **Single price override.** Every STAMMDATEN price bridge reads `baustoff.basispreis_eur`, so
  one `model_copy` covers `materialpreis_eur_pro_t`, `asphalt_preis_eur_pro_t`, `pmb_*`,
  `gussasphalt_*`, `dsk_*`, `grid_*`, `abstreukoernung_*`, `fugenmasse_*`, `randabdichtung_*`
  with no per-variable wiring.
- **Distance precedence.** `bind_lieferant` → `lieferant_werte` → shown as the Gate B proposal
  (collapsed) → **Gate B user override wins** → `compute`. When no supplier is bound,
  `entfernung_lieferant_km` falls back to its 10 km default (existing behaviour).
- **Provenance (no new `AufloesungsMethode`).** Supplier price and distance use `quelle =
  STAMMDATEN` with explicit `beleg` ("Lieferant X (Ort), Werkspreis … frei Werk, Stichtag …" and
  "X (Ort) → Baustelle, N km (Google Routes)").
- **Determinism preserved.** Geocoding/routing are I/O confined to graph nodes; the engine
  (`Kalkulator.resolve` / `eval_ausdruck`) stays pure and runs on a pre-filled `ctx.werte`.

---

## Tests

**Added**
- `tests/unit/maps/test_geo.py` — geocode mock + live parse + no-key/zero-result errors;
  route_matrix mock (haversine) + live parse with per-pair haversine fallback + HTTP-error
  wrap; `road_distance_km`.
- `tests/unit/services/test_lieferant_ranking.py` — cheapest-delivered ordering, agreement with
  the offline `guenstigster_lieferant` baseline, `top_n` cap, empty for uncarried/unknown
  material.
- `tests/unit/services/test_calculator_graph.py` — `test_supplier_drives_material_price_and_antransport`
  (supplier price override + Antransport distance both reach the EKT and audit) and
  `test_gate_a_supplier_pick_is_honoured`.

**Updated** (to the split variable names)
- `tests/unit/services/test_kalkulation_v2.py` — fräsen leaf set → `entfernung_deponie_km`; STS
  fixture → `entfernung_lieferant_km`.
- `tests/unit/services/test_calculator_graph_live.py` — collapsed → `entfernung_deponie_km`.
- `tests/unit/services/test_calculator_graph.py` — docstring + `lieferanten_vorschlag == {}` for
  the material-free fräsen position.

> Note: `tests/unit/eval/test_grade_chat.py` keeps `entfernung_km` as a generic grading example
> (it is not catalog-bound), so it was intentionally left unchanged.

---

## Verification

The build sandbox has **no `uv` / `.venv` / `pytest` / `pydantic_settings`** and an **empty
`ui/node_modules`**, so only the config-free `kalkulation_v2` engine could be executed.

**Run and passing (direct execution):**
- `store.py` `__main__` computes the full EKT table; **EKT gesamt 557933.35** across 41 positions
  (unchanged — the split preserved the 10 km defaults).
- Worklist routing: fräsen → `entfernung_deponie_km`; FSS/Asphalt → `entfernung_lieferant_km`;
  old `entfernung_km` removed from the catalog; Baustelle coords present.
- `lade_preise` attaches 515 price rows; `guenstigster_lieferant` returns a sensible ranking.
- Fräsen worklist matches the updated test set exactly; STS fixture computes.
- `py_compile` passes for **all** new and changed backend + test files.

**Not run in the sandbox (needs your environment):**
- The pytest suite for the graph, maps client, and ranker (they import `shared.config`).
- UI type-check / build (`node_modules` is empty).

### How to verify

```bash
# Backend
uv sync
uv run pytest tests/unit/services/test_calculator_graph.py \
              tests/unit/services/test_calculator_graph_live.py \
              tests/unit/services/test_lieferant_ranking.py \
              tests/unit/services/test_kalkulation_v2.py \
              tests/unit/maps/test_geo.py

# UI
cd ui && npm install && npm run build      # tsc -b + vite
```

---

## Caveats, deferred items, and open questions

- **Live address extraction is pragmatic.** `locate_baustelle` reuses the RAG retriever + the
  Geocoding API (the plan's allowed shortcut) instead of a dedicated extraction LLM site; a road
  segment ("L 101 bei Nordhausen") geocodes with variable confidence. Low confidence is flagged
  for HITL at Gate A. A dedicated extraction `PromptType` is a clean future refinement.
- **Geocoding is per-position**, gated to positions with a material. Project-level location
  caching is deferred (no project-level shared context yet — plan §9).
- **Routes API cost/quota.** Mitigated by a haversine pre-filter + Route Matrix on the top-N and
  a per-pair haversine fallback; **result caching is not yet implemented**.
- **Deponie distance unchanged.** `entfernung_deponie_km` stays HITL + 10 km default; disposal-site
  selection is out of scope. The split makes a future symmetric "Deponie selection" easy.
- **Supplier price coverage gaps.** Where no supplier carries a Baustoff (e.g. some
  asphalt/bitumen/specialty mixes), `bind_lieferant` binds nothing → the catalog `basispreis_eur`
  and the default Antransport distance apply (current behaviour).
- **Multi-material positions.** Payload/answer/state are keyed per `baustoff_code` for
  forward-compatibility; today the model is one material per position.
- **Provenance vocabulary.** No dedicated `GEOCODE`/`ROUTING` `AufloesungsMethode` — supplier
  price/distance reuse `STAMMDATEN` + explicit `beleg`. Revisit only if auditors need those
  sources distinguished on the Nachweistabelle.
- **Stichtag.** Supplier prices load with `gueltig_ab = 2026-01-01`; the calc `STICHTAG`
  (`2026-06-22`) resolves against them.
- **Maps key naming.** The Geocoding/Routes client reuses `settings.google_static_maps_api_key`
  (the same Google Maps Platform key as the static-map chat tool); the field name is historical.

---

## File inventory

**New**
- `server/shared/clients/maps/geo.py`
- `server/shared/services/calculator/lieferant_ranking.py`
- `tests/unit/maps/test_geo.py`
- `tests/unit/services/test_lieferant_ranking.py`

**Changed**
- `server/shared/clients/maps/__init__.py`
- `server/shared/config.py`
- `server/shared/services/calculator/graph.py`
- `server/shared/services/calculator/state.py`
- `server/shared/services/kalkulation_v2/formel.py`
- `server/shared/services/kalkulation_v2/kontext_variablen.py`
- `server/shared/services/kalkulation_v2/positionen.py`
- `server/shared/services/kalkulation_v2/store.py`
- `tests/unit/services/test_calculator_graph.py`
- `tests/unit/services/test_calculator_graph_live.py`
- `tests/unit/services/test_kalkulation_v2.py`
- `ui/src/api/calculations.ts`
- `ui/src/views/workspace/InterruptPanel.tsx`

---

## Coverage vs the plan (`LIEFERANTENWAHL_PLAN.md` §6)

| Plan item | Status |
|-----------|--------|
| 6.1 Maps client (Geocoding + Routes, mock) | Done (`clients/maps/geo.py`) |
| 6.2 Load supplier prices (`lade_preise` in store) | Done |
| 6.3 New context variables (Baustelle coords, split distance) | Done |
| 6.4 Formula rewiring (5 `trans_*`) | Done |
| 6.5 Async supplier ranker | Done (`lieferant_ranking.py`) |
| 6.6 Graph wiring (`locate_baustelle`, `bind_lieferant`, Gate A, compute override) | Done |
| 6.7 State fields | Done |
| 6.8 Provenance / Nachweis | Done (price + distance beleg; supplier on the audit) |
| 6.9 UI Gate A supplier picker | Done (`gen:types` not required) |
| 6.10 Config / settings | Done (Maps URLs + timeout; key reuse; Stichtag confirmed) |
| 6.11 Tests | Unit + mock-integration added; **suite not yet run** |
| 6.6 `run_service` capture of Gate A pick | Not needed (flows via resume) |
| Integration/eval (live graph run; supplier-vs-catalog EKT delta) | Not added (optional) |
