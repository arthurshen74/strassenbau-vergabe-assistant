# Lieferantenwahl — Supplier Selection in the Calculation Agent (Plan)

Status: **Plan only** — no code changes made. This document is the implementation
plan for wiring **Lieferant (supplier) selection** into the EKT position-calculation
StateGraph, so that material cost and haul distance become **supplier-driven** and
the **Baustelle location** is resolved by geocoding the Baubeschreibung.

Companion reading: `server/shared/services/kalkulation_v2/ARCHITECTURE.md` (§5
materials/suppliers, §7 the StateGraph). This plan realizes two items that doc
already anticipates: the "future supplier-price table" (§5) and the
"swap in OSRM/Google for road distance" note (§5 `lieferanten.py`).

---

## 1. Goal

Today the calculator selects a **Baustoff** (Gate A) but never a **Lieferant**.
Material cost is the Baustoff's catalog base price (`baustoff.basispreis_eur`), and
the material haul distance (`entfernung_km`) is a HITL value with a 10 km default.
The supplier catalog (`LIEFERANTEN`, 52 firms with real coordinates), the static
price list (`lieferanten_preise.PREISE`), and the cheapest-delivered ranker
(`materialien.guenstigster_lieferant`) all exist but are **never called in running
code** — only in `__main__` demos.

After this change, for each material in a position the estimator picks a supplier at
**Gate A** (cheapest delivered pre-selected, overridable). The chosen supplier drives
**two existing cost inputs**:

1. the **ex-works material price** (replaces the catalog base price), and
2. the **inbound haul distance** for the Antransport cost line (real road distance).

## 2. Decisions locked (with the user)

- **Baustelle location** is a pair of **required context variables**:
  `baustelle_breitengrad`, `baustelle_laengengrad` — two plain `Decimal`
  kontext-variables, **no new coordinate type**. Resolved by geocoding the
  Baubeschreibung. "Required" = no silent KONSTANTE default; must resolve before
  compute (it drives supplier ranking).
- **Supplier is chosen at Gate A**, **per material**, with a **default** supplier
  (cheapest delivered) pre-selected and overridable — consistent with the existing
  Gate A machine/Baustoff pickers.
- **Geocoding + Routing** use the existing **Google Maps Platform API key**
  (`MAP_API`, project `roadbuilders-document-assist`). Confirmed enabled:
  **Geocoding API** and **Routes API**.
- **No new `AufloesungsMethode`** for geocode/routing (no "type overkill"). Resolved
  values reuse existing `quelle` vocabulary with an explicit `beleg`; a dedicated
  GEOCODE/ROUTING provenance is deferred (see §9).

## 3. Key insight — supplier drives two inputs, no double-counting

Recipes already keep **Material** and **Antransport** as **separate cost lines**
(`server/shared/services/kalkulation_v2/vorgaenge.py`,
`server/shared/services/kalkulation_v2/formel.py:51-53, 94-98`):

```
materialkosten        = tonnage_material * materialpreis_eur_pro_t   # ex-works price
trans_material        = tonnage_material * transport_eur_pro_t_km * entfernung_km
materialkosten_asphalt= menge_t * asphalt_preis_eur_pro_t
trans_asphalt         = menge_t * transport_eur_pro_t_km * entfernung_km
```

So the material price is **ex-works (frei Werk)** and transport is costed
separately. Selecting a supplier therefore feeds **both** existing inputs and does
**not** double-count:

- **Price** → the supplier's ex-works €/t replaces `baustoff.basispreis_eur`.
- **Distance** → the supplier→Baustelle road distance fills the Antransport distance.

The selection criterion remains **cheapest delivered** =
`werkspreis + transport_eur_pro_t_km · road_km` (what `guenstigster_lieferant` already
computes), but for the EKT we split it back into the two auditable lines.

## 4. Correctness fix — split `entfernung_km`

`entfernung_km` (bezeichnung "Entfernung Lager/Deponie",
`kontext_variablen.py`) is currently **shared** by inbound supply and outbound
disposal transport:

| Cost line        | Kostenart   | Direction                | Distance should be |
|------------------|-------------|--------------------------|--------------------|
| `trans_material` | ANTRANSPORT | supplier → Baustelle     | supplier distance  |
| `trans_asphalt`  | ANTRANSPORT | mixing plant → Baustelle | supplier distance  |
| `trans_boden`    | ABTRANSPORT | Baustelle → Deponie      | disposal distance  |
| `trans_fraesgut` | ABTRANSPORT | Baustelle → Deponie/RC   | disposal distance  |
| `trans_aufbruch` | ABTRANSPORT | Baustelle → Deponie      | disposal distance  |

Overriding the single `entfernung_km` with the supplier distance would wrongly move
disposal costs. **Split it into two context variables:**

- `entfernung_lieferant_km` — Antransport, supplier → Baustelle. **Filled by supplier
  selection** (Routes API). HITL fallback if unresolved.
- `entfernung_deponie_km` — Abtransport, Baustelle → Deponie. **Unchanged behaviour**
  (HITL + 10 km default); a future "Deponie selection" can fill it the same way the
  supplier fills the inbound side.

Rewire the formulas: `trans_material`/`trans_asphalt` → `entfernung_lieferant_km`;
`trans_boden`/`trans_fraesgut`/`trans_aufbruch` → `entfernung_deponie_km`. Update the
position fixtures and any pinned `entfernung_km` kontext values accordingly.

## 5. Architecture — where geocoding/routing live

The pure engine (`model.py` `eval_ausdruck`/`Kalkulator.resolve`) must stay
deterministic and I/O-free (ARCHITECTURE §1, §2). Geocoding and routing are I/O, so
they live in **graph nodes** (a new client), and they fill **resolved
`VariablenWert`s into `ctx.werte` before compute** — exactly the existing
"StateGraph fills LANGTEXT/RAG/HITL before calc" seam (`Kalkulator.resolve` step 3,
`graph.py` `bind_resources` already does this for machine rates via `maschinen_werte`).

```
launch
  -> extract_chat_values
  -> classify_leistung
  -> locate_baustelle        (NEW: address from Baubeschreibung -> Geocoding -> lat/lon)
  -> method_review           (Gate A: + per-material supplier picker, default = cheapest delivered)
  -> bind_resources          (machines + baustoff, unchanged)
  -> bind_lieferant          (NEW: finalize supplier -> werkspreis override + entfernung_lieferant_km)
  -> derive_required_variables
  -> resolve_variables
  -> variable_review         (Gate B, unchanged)
  -> compute                 (apply baustoff price override + injected distances)
  -> render_output
```

`locate_baustelle` runs before Gate A because supplier ranking needs the site
coordinates. It is **project-level** (same for every position); for now resolve
per-position, with cross-position caching deferred (ARCHITECTURE §9: no project-level
shared context yet).

## 6. Work breakdown

### 6.1 New Maps client — `server/shared/clients/maps/`
- Wrap Google **Geocoding API** + **Routes API** (key from `MAP_API`).
- `geocode(address: str) -> GeocodeResult(lat: Decimal, lon: Decimal, formatted: str, confidence: float)`.
- `road_distance_km(origin, dest) -> Decimal` and a **batch** `route_matrix(origins, dests)`
  (Routes API Route Matrix) so one call ranks N candidate suppliers.
- **Mock mode** (`settings.calculator_mock`): deterministic stubs — geocode returns a
  fixed fixture coordinate (e.g. the demo `51.42, 10.81`); distance falls back to the
  existing haversine helper `lieferanten.entfernung_km` (×1.3). Keeps the whole offline
  flow runnable, per the calculator's mock-mode contract (`graph.py` header).
- Config: reuse `MAP_API`; add base URLs + timeout to `shared/config`.

### 6.2 Load supplier prices
- `lieferanten_preise.lade_preise(BAUSTOFFE, LIEFERANTEN)` is **never called** outside
  `__main__`. Call it once at catalog assembly in
  `server/shared/services/kalkulation_v2/store.py` so `LIEFERANTEN[*].preise` is
  populated for the running agent. (ARCHITECTURE §5 calls PREISE "the future
  supplier-price table".)
- Coverage gap (ARCHITECTURE §5): asphalt mixes / bitumen / per-Einheit specialties
  (DSK €/m², grid €/m², Randabdichtung €/m, Fugenmasse) may lack supplier rows. Where
  the chosen supplier has **no** price for the Baustoff, **fall back to the catalog
  `basispreis_eur`** (current behaviour) and surface a reasoning note.

### 6.3 New context variables — `kontext_variablen.py`
- `baustelle_breitengrad`, `baustelle_laengengrad`: required (no KONSTANTE default;
  always-surfaced / high-stakes like `fraesgut_klasse`). Filled by `locate_baustelle`.
- `entfernung_lieferant_km`: HITL + default fallback; filled by `bind_lieferant`.
- `entfernung_deponie_km`: rename/clone of today's `entfernung_km` (HITL + 10 km
  default). Remove the old shared `entfernung_km` once formulas are rewired.

### 6.4 Formula rewiring — `formel.py`
- `trans_material`, `trans_asphalt` → `entfernung_lieferant_km`.
- `trans_boden`, `trans_fraesgut`, `trans_aufbruch` → `entfernung_deponie_km`.

### 6.5 Supplier ranking (service-level, async)
- Add an async ranker that, given `baustoff_code` + Baustelle coords, returns
  suppliers sorted by **delivered** price using the Maps client for **road** distance
  (Route Matrix), falling back to haversine.
- Efficiency: pre-filter to the N nearest by haversine (`naechste_lieferanten`) that
  **carry the Baustoff** (`preis_fuer`), then route-matrix only those (e.g. top 10).
- Keep `materialien.guenstigster_lieferant` (sync/haversine) as the offline baseline.

### 6.6 Graph wiring — `server/shared/services/calculator/graph.py`
- **`locate_baustelle` node** (after `classify_leistung`): retrieve the site address
  from the Baubeschreibung (existing retriever + an extraction prompt, or reuse the
  RAG step), geocode it, write the two coordinate `VariablenWert`s into state/`werte`.
  Stream reasoning. Unresolved → flag for HITL (surface at Gate A or a small prompt).
- **Gate A (`method_review`)**:
  - Payload: add `lieferanten_vorschlag` — for the proposed Baustoff, the ranked
    supplier list (`code, name, ort, werk_eur_pro_t, strasse_km, frei_bau_eur_pro_t`)
    with `default` = cheapest. **Keyed by material (`baustoff_code`)** so a
    multi-material position is forward-compatible (today: one material → one picker).
  - Answer: add `lieferant_code` (per material).
- **`bind_lieferant` node** (after `bind_resources`): given the **final**
  `baustoff_code` + coords, finalize the supplier — honour the Gate A `lieferant_code`
  **iff** that supplier carries the final Baustoff, else auto-pick cheasest (mirror of
  the machine-pick fallback `picks.get(slot) or kand[0]`). Then:
  - **Price**: stash the supplier ex-works €/t so compute can override the Baustoff
    price (see 6.7).
  - **Distance**: write `entfernung_lieferant_km` as a resolved `VariablenWert`
    (`beleg = "Lieferant X (Ort) -> Baustelle, N km (Google Routes)"`).
  - Stream reasoning (e.g. "Lieferant X: Werk 17,50 €/t + 14,2 km -> 19,20 €/t frei
    Baustelle; günstigster von 6").
- **`compute` node**: build `stammdaten["baustoff"]` from
  `BAUSTOFFE[bc].model_copy(update={"basispreis_eur": werk, "basispreis_eur_pro_t": werk})`
  when a supplier price exists — this **single override flows through every STAMMDATEN
  price bridge** (`materialpreis_eur_pro_t`, `asphalt_preis_eur_pro_t`, `pmb_*`,
  `gussasphalt_*`, `dsk_*`, etc.) with no per-variable wiring. Inject the distance
  `VariablenWert` alongside `maschinen_werte`/`werte` as already done.

### 6.7 State — `server/shared/services/calculator/state.py`
- Add: `baustelle_breitengrad`, `baustelle_laengengrad`,
  `lieferanten_vorschlag` (ranked list, per baustoff), `gewaehlter_lieferant`
  (baustoff_code → lieferant_code), `lieferant_werkspreis` (the override), and the
  supplier-sourced distance value. Keep all JSON-serializable (Decimals as strings)
  for the Postgres checkpointer, per the existing state contract.

### 6.8 Provenance / Nachweis
- Material-cost line: tag the supplier-driven price with `quelle = STAMMDATEN`
  (supplier price **is** master data) and `beleg = "Lieferant X (Ort), Werkspreis frei
  Werk, Stichtag …"`. Distance: `quelle` reused + explicit `beleg` (see §9).
- Add the chosen supplier + werkspreis + road km to the Nachweistabelle / reasoning so
  the EKT stays auditable (which supplier, what price, what distance).

### 6.9 UI — Gate A supplier picker
- New React component for the per-material supplier picker in the Gate A interrupt
  (ranked list, default highlighted, shows werk €/t · km · frei-Bau €/t). Wire into the
  existing Gate A dispatch (`STAGE_METHOD_REVIEW`). Regenerate `types/generated.ts`
  (`npm run gen:types`) after the schema changes. Reference: ARCHITECTURE §7 "HITL
  Gates" (custom React components preferred over text-only gates).

### 6.10 Config / settings
- `MAP_API` key (reuse), Maps base URLs + timeout, mock toggle wiring.
- Confirm the supplier-price `STICHTAG` (`materialien.STICHTAG = 2026-06-22`) vs
  `lade_preise` default `gueltig_ab = 2026-01-01` so `preis_fuer` resolves.

### 6.11 Tests / eval
- Unit: ranker selection + haversine/Routes fallback; `bind_lieferant` honour-pick vs
  fallback; price override flows through all bridges; distance feeds
  `entfernung_lieferant_km` only (disposal lines unaffected); mock geocode/route stubs.
- Integration: full graph run on a fixture position yielding a supplier-driven EKT,
  asserting Material **and** Antransport lines both reflect the chosen supplier.
- Eval (optional): supplier-driven vs catalog-base EKT delta on the L 101 fixture.

## 7. End-to-end data flow

1. `locate_baustelle`: Baubeschreibung → address → **Geocoding** → Baustelle lat/lon.
2. `classify_leistung`/Gate A: Baustoff proposed (BM25) as today.
3. Gate A payload: rank suppliers carrying the proposed Baustoff by **delivered** price
   (**Routes** road distance) → per-material picker, cheapest default.
4. Gate A answer: estimator confirms/overrides `lieferant_code` per material.
5. `bind_lieferant`: re-validate vs final Baustoff → werkspreis override +
   `entfernung_lieferant_km`.
6. `compute`: Baustoff price = supplier werkspreis (all bridges); Antransport uses the
   supplier road distance; Abtransport unchanged (`entfernung_deponie_km`).
7. `render_output`/Nachweis: supplier, werkspreis, road km on the audit trail.

## 8. Touched files (checklist)

- `server/shared/clients/maps/` — NEW (Geocoding + Routes client, mock stubs).
- `server/shared/config` — `MAP_API` + Maps settings.
- `server/shared/services/kalkulation_v2/store.py` — call `lade_preise(...)`.
- `server/shared/services/kalkulation_v2/kontext_variablen.py` — Baustelle coords;
  split `entfernung_km` → `entfernung_lieferant_km` / `entfernung_deponie_km`.
- `server/shared/services/kalkulation_v2/formel.py` — rewire the 5 `trans_*` lines.
- `server/shared/services/kalkulation_v2/materialien.py` / a new service — async ranker.
- `server/shared/services/kalkulation_v2/positionen.py` — fixtures: rename pinned
  `entfernung_km`.
- `server/shared/services/calculator/graph.py` — `locate_baustelle`, `bind_lieferant`,
  Gate A payload/answer, `compute` override.
- `server/shared/services/calculator/state.py` — new state fields.
- `server/shared/services/calculator/run_service.py` — capture the Gate A
  `lieferant_code` on resume (mirrors `_capture_gate_b`), if needed.
- UI: Gate A supplier-picker component + `npm run gen:types`.
- Tests under `tests/unit` + `tests/integration`; optional `eval/`.

## 9. Open questions / risks / deferred

- **Provenance vocabulary.** Per the no-overkill decision, no new `AufloesungsMethode`.
  Geocoded coords / routed distance reuse an existing `quelle` (likely `RAG` for coords
  from the document, `STAMMDATEN` for supplier price/distance) with an explicit `beleg`.
  A dedicated `GEOCODE`/`ROUTING` provenance is **deferred** — revisit only if auditors
  need those sources distinguished on the Nachweistabelle.
- **Project-level location caching.** Geocoding per position is wasteful (location is
  project-level). Deferred until a project-level shared-context layer exists
  (ARCHITECTURE §9).
- **Routes API cost/quota.** Mitigate with haversine pre-filter + Route Matrix on top-N
  + result caching; haversine fallback on failure or mock mode.
- **Disposal-site (Deponie) selection.** Out of scope here; `entfernung_deponie_km`
  stays HITL/default. The split (§4) makes a future Deponie-selection symmetric to the
  supplier side.
- **Address extraction reliability.** Baubeschreibung may state a road/segment (e.g.
  "L 101 bei Nordhausen") rather than a postal address; geocoding confidence varies.
  On low confidence, surface for HITL confirmation at Gate A rather than trust silently.
- **Supplier price coverage** for asphalt/bitumen/specialties — fall back to catalog
  `basispreis_eur` where missing (ARCHITECTURE §5 flags asphalt as the highest-value
  calibration gap).
- **Multi-material positions.** Current model is one `baustoff_code` per position; the
  Gate A picker is keyed per material to stay forward-compatible.
