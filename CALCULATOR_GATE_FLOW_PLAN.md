# Calculator Gate-Flow Redesign — Four HITL Gates, Resolve-on-Confirmed (Plan)

Status: **Plan only** — no code changes. This document specifies a restructuring of the EKT
position-calculation StateGraph so that every resolution step runs **only on inputs the human has
already confirmed**. It replaces the current 3-gate flow with **4 gates** and moves geocoding and
supplier ranking to the correct points in the sequence.

Companion reading: `server/shared/services/calculator/graph.py` (the graph), `state.py` (stages +
state), `PROJECT_CONTEXT_PLAN.md` (§8 topology this evolves), `LIEFERANTENWAHL_PLAN.md` (supplier
ranking this reorders).

---

## 1. Motivation — the ordering bugs

Two dependency inversions in the current graph produce wrong numbers:

1. **Supplier ranking runs before the material is confirmed.** `rank_lieferanten` fires against the
   *proposed* Baustoff (before Gate A). When the estimator corrects the Baustoff at Gate A,
   `bind_lieferant` looks up a ranked list keyed by the corrected code, finds none, and silently
   falls back to the catalog base price + the 10 km default distance. Observed: an EKT priced from
   the catalog with no Lieferant, exactly for the positions where the human fixed the material.

2. **Material is proposed before the Bauverfahren is confirmed.** The BM25 Baustoff match can't be
   scoped to a recipe that isn't locked yet, so an asphalt-laying position matched raw
   `BITUMEN_50_70` (a `Bindemittel`, ~580 €/t) instead of `ASPHALT_AC32TS` (an `Asphaltmischgut`,
   72 €/t) because the position text emphasised "Bitumen 50/70". The bitumen price then flowed into
   the asphalt material-cost bridge (and, because every supplier now carries every tonnage material
   after the full-coverage gap-fill, the nearest aggregate supplier "won" the bitumen ranking at
   524.90 €/t).

**Redesign principle:** a resolve step must consume only confirmed inputs. Geocode after a location
is resolved/changed; propose material after the Bauverfahren is confirmed; rank suppliers after the
material is confirmed.

---

## 2. Locked decisions

- **A — Geocoding lives in Gate 1, on the fly.** `resolve_project_context` emits location **strings
  only**. Gate 1 geocodes on entry (shows a map per location) and re-geocodes edits live via an
  **"Ändern" button + modal**, repainting the map before confirm. Invariant: *a geocode happens
  whenever a location is resolved or changed.* No separate post-gate geocode node. The
  Baustelle→Deponie distance is routed on confirm.
- **A+ (new) — Show the route.** Gate 1 shows **three maps**: Baustelle (point), Deponie (point), and
  the **Baustelle→Deponie route** (road polyline) on its own map. The route map updates when either
  location changes.
- **B — Material and supplier are separate gates.** Material is confirmed at Gate 3; the supplier is
  picked at Gate 4 (the ranked list only exists after the material is confirmed and the site is
  geocoded).
- **C — Gate 2 is Leistung + Bauverfahren only.** Machines leave the method gate.
- **D — No auto-advance (yet).** Every gate stops, always. Err on the side of caution; revisit later.
- **E — Material gate = acquisition only.** The Gate-3 Baustoff is the acquired material that drives
  Lieferant selection. Disposal/removal keeps its existing flow (Deponie is a project global;
  `fraesgut_klasse` + `entfernung_deponie_km` surface at the variable gate). The gate is **skipped**
  for material-free positions (`braucht_baustoff` false — e.g. Fräsen).

---

## 3. Topology — current vs proposed

### Current (3 gates)
```
launch → extract_chat_values
  → load_project_context      (resolve + GEOCODE baustelle/deponie + route deponie)
  → project_context_review    [GATE 1]
  → classify_leistung         (Leistung + BV candidates + BM25 Baustoff)
  → rank_lieferanten          (rank suppliers for the PROPOSED Baustoff)
  → method_review             [GATE 2 = Gate A: Leistung, BV, Maschinen, Baustoff, Lieferant]
  → bind_resources → bind_lieferant
  → derive_required_variables → resolve_variables
  → variable_review           [GATE 3 = Gate B]
  → compute → render_output
```

### Proposed (4 gates)
```
launch → extract_chat_values
  → resolve_project_context   (RAG synthesis → location/dim STRINGS; no geocode)
  → project_context_review    [GATE 1] geocode on the fly + 3 maps (Baustelle, Deponie, Route);
                                        confirm persists {address, coords, status}; routes Deponie;
                                        blocks/loops if required Baustelle has no coords
  → classify_leistung         (Leistung + Bauverfahren candidates ONLY — no material)
  → leistung_bv_review        [GATE 2] confirm Leistung + pick Bauverfahren (cancel aborts)
  → resolve_material          (propose Baustoff given the confirmed BV; skip if braucht_baustoff=false)
  → material_review           [GATE 3] confirm/override Baustoff        (skipped for material-free)
  → rank_lieferanten          (rank suppliers for the CONFIRMED Baustoff + confirmed Baustelle coords)
  → bind_resources → bind_lieferant   (right-size machines per BV slot; default = cheapest supplier)
  → derive_required_variables → resolve_variables  (machines + supplier price/distance + globals → proposals)
  → variable_review           [GATE 4] machines + supplier picker + all other leaves (tiered)
  → compute → render_output
```

Routing/edges:
- **Gate 1 block-loop** (unchanged mechanism): a required global (Baustelle) without valid coords
  loops back to `project_context_review`; cancel aborts to `END`.
- **Gate 2 cancel** → `END` (mirror of today's `_route_after_method` abort).
- **Material conditional:** `resolve_material` decides whether a Baustoff is needed
  (`braucht_baustoff(BV)`); if yes → `material_review`; if no → straight to `rank_lieferanten`
  (which no-ops without a Baustoff).

---

## 4. The four gates

### Gate 1 — `project_context_review` (evolved)
- Payload adds nothing structurally beyond today (`projekt_kontext`, `reconcile`, `project_uuid`,
  `fehler`), but the UI now **owns geocoding**:
  - On mount, geocode the resolved Baustelle/Deponie strings via the new geocode endpoint and render
    a point map each.
  - **Route map:** when both coords exist, render the Baustelle→Deponie road route on a third map.
  - **"Ändern" modal** per location: edit the address → geocode on the fly → preview the new point
    map + coords + status → confirm → the gate's location, its point map, and the route map update.
- Resume sends, per location, `{address, breitengrad, laengengrad, status}` (coords come from the
  modal's geocode — the saver trusts them and does **not** re-geocode), plus strip dims + Fräsgut.
- Saver routes the Baustelle→Deponie distance (`entfernung_deponie_km`) once both coords are settled.
- Blocking unchanged: required-global (Baustelle) without valid coords re-loops with `fehler`.

### Gate 2 — `leistung_bv_review` (new; split from `method_review`)
- Payload: `leistung_key`, `leistung_name`, the full Leistung catalog (so an unclassified position
  can still be assigned), `bauverfahren_kandidaten`.
- Answer: `leistung_key` (optional correction, re-derives candidates), `bauverfahren_key`, `cancel`.
- No machines, no material here.

### Gate 3 — `material_review` (new; conditional)
- Reached only when the confirmed Bauverfahren needs an acquisition Baustoff.
- Payload: `baustoff_vorschlag` (BM25 top hit + alternates + `auto` flag), produced by
  `resolve_material` **after** the BV is known.
- Answer: `baustoff_code`.
- Skipped entirely for material-free recipes.

### Gate 4 — `variable_review` (evolved from Gate B)
- Now also carries the **supplier picker** (`lieferanten_vorschlag`, keyed by the confirmed Baustoff)
  and machines, alongside the tiered leaf variables.
- The supplier's ex-works price and inbound road distance appear as overridable proposals; changing
  the supplier pick re-applies that offer's price + distance (see §6).

---

## 5. Geocoding + maps (Gate 1)

Three render surfaces, all backed by the existing/added maps clients:

| Surface | Source | Endpoint |
|---|---|---|
| Baustelle point map | geocoded coords | `GET /context/map?lat&lon` (exists) |
| Deponie point map | geocoded coords | `GET /context/map?lat&lon` (exists) |
| **Baustelle→Deponie route map** | route polyline | `GET /context/route-map?...` (**new**) |
| "Ändern" modal geocode | Geocoding API | `GET /context/geocode?address=…` (**new**) |

New endpoints (`api/routes/project_contexts.py`):
- **`GET /projects/{id}/context/geocode?address=…`** → `{breitengrad, laengengrad, formatiert,
  konfidenz, status}`. Wraps `clients/maps/geo.geocode`. Mock returns the fixture coordinate. Lets
  the modal resolve an edited address without a full save.
- **`GET /projects/{id}/context/route-map?origin_lat&origin_lon&dest_lat&dest_lon`** → PNG. Fetches
  the road polyline via a new Routes-API `computeRoutes` call, renders a Static Map with
  `path=enc:{polyline}` + a marker at each end. 502 on failure (same as the point map).

New maps-client work (`clients/maps/`):
- `geo.route_polyline(origin, dest) -> (Decimal_km, str_encoded_polyline)` via Routes API
  **`computeRoutes`** (`directions/v2:computeRoutes`, field mask
  `routes.distanceMeters,routes.polyline.encodedPolyline`). Add
  `settings.google_maps_compute_routes_url`.
- `client.fetch_route_map_png(origin, dest, polyline) -> bytes` — Static Maps with `path=enc:` +
  two markers. Reuses `settings.google_static_maps_api_key`.
- Mock mode: `route_polyline` returns the haversine distance and a straight two-point path so the
  offline flow still renders a (straight-line) route map.

Optimization (optional): the Deponie leg is already routed for `entfernung_deponie_km`. Switch that
leg from `computeRouteMatrix` to `computeRoutes` so one call yields **distance + polyline**, cache
the polyline on the `entfernung_deponie_km` value's `quelle_referenz`, and have `route-map` render
from the cached polyline. Supplier legs keep using `computeRouteMatrix` (batch, no polyline needed).

---

## 6. Supplier ranking moves after material

- `rank_lieferanten` runs **after** `material_review`, keyed by the **confirmed** `baustoff_code`
  and the **confirmed** Baustelle coords. No stale list; no `bind_lieferant` re-rank hack.
- `bind_lieferant` sets the default = cheapest-delivered; `resolve_variables` exposes the supplier's
  ex-works price (`asphalt_preis_eur_pro_t` / `materialpreis_eur_pro_t` bridge via
  `_effektiver_baustoff`) and `entfernung_lieferant_km` as Gate-4 proposals.
- **Supplier override at Gate 4:** the ranked `lieferanten_vorschlag` stays in state; a Gate-4 pick
  updates `gewaehlter_lieferant`; on resume, the chosen offer's werkspreis + road distance are
  re-applied (the honour-pick logic currently in `bind_lieferant`, moved to run against the Gate-4
  answer) before `compute`. Material-free positions and uncovered materials fall back to the catalog
  price + default distance exactly as today.

---

## 7. State + stages (`state.py`)

- Stages: keep `STAGE_PROJECT_CONTEXT_REVIEW`; **add** `STAGE_LEISTUNG_BV_REVIEW`,
  `STAGE_MATERIAL_REVIEW`; keep `STAGE_VARIABLE_REVIEW`. Remove `STAGE_METHOD_REVIEW`.
- Fields: `baustoff_vorschlag` now produced by `resolve_material` (post-BV). `lieferanten_vorschlag`
  produced by `rank_lieferanten` (post-material). No new persistence for the route (rendered on
  demand) unless the caching optimization in §5 is taken.
- Keep everything JSON-serialisable for the Postgres checkpointer.

## 8. Touched files (checklist)

- `server/shared/services/calculator/graph.py` — split `method_review` → `leistung_bv_review` +
  `material_review`; new `resolve_material`; `resolve_project_context` (no geocode); move
  `rank_lieferanten`/`bind_lieferant` after material; conditional edges; supplier apply at Gate 4.
- `server/shared/services/calculator/state.py` — stage constants + field docs.
- `server/shared/services/calculator/run_service.py` — capture the two new gate answers on resume.
- `server/shared/services/project_context/service.py` — `save` trusts modal coords (still geocodes
  when only an address is supplied); resolve emits strings.
- `server/shared/clients/maps/geo.py` — `route_polyline` (computeRoutes).
- `server/shared/clients/maps/client.py` — `fetch_route_map_png` (path=enc).
- `server/shared/config.py` — `google_maps_compute_routes_url`.
- `server/api/routes/project_contexts.py` — `GET /context/geocode`, `GET /context/route-map`.
- `ui/src/views/workspace/InterruptPanel.tsx` — `LeistungBvReview`, `MaterialReview` components;
  supplier picker moves to `VariableReview`; `ProjectContextReview` gains the "Ändern" modal + three
  maps.
- `ui/src/api/project-context.ts` / `calculations.ts` — geocode hook; resume shapes for the new gates.
- Tests under `tests/unit/services` (graph gates), `tests/unit/maps` (route_polyline / route map),
  `tests/integration/api` (geocode + route-map endpoints).

---

## 9. Phasing

**Phase 1 — gate split + ranking-after-material (the correctness fix).** Split the method gate into
Gate 2 (Leistung/BV) and conditional Gate 3 (Material); add `resolve_material`; move
`rank_lieferanten`/`bind_lieferant` after Gate 3; relocate the supplier picker into Gate 4. Graph +
state + run_service + UI (two new gate components; picker moves) + graph tests. Delivers the
`524.90`/catalog-fallback fix on its own. Verify each gate with a graph test before the UI.

**Phase 2 — geocoding UX + maps (A / A+).** `resolve_project_context` stops geocoding; add the
`geocode` and `route-map` endpoints + `route_polyline`/`fetch_route_map_png`; Gate 1 gets the
"Ändern" modal (live geocode + point map) and the third **route map**; the saver trusts modal coords
and routes the Deponie leg. Independent of Phase 1 — can land before or after.

The phases are independently shippable and testable.

---

## 10. Testing

- Unit (graph): Gate 2 confirms Leistung/BV; Gate 3 confirms Baustoff; **correcting the Baustoff at
  Gate 3 makes `rank_lieferanten` run on the corrected material** (the regression that motivated
  this — assert supplier-driven price + routed distance, not catalog fallback); material-free
  position skips Gate 3 and ranking; Gate 2 cancel aborts.
- Unit (maps): `route_polyline` mock (straight line) + live parse; `fetch_route_map_png` builds
  `path=enc`.
- Integration (api): `context/geocode` returns coords/status (mock) and 502 on `MapsError`;
  `context/route-map` returns PNG (stubbed) and 502 without a key.
- UI: build (`tsc -b`); the three gates dispatch; the "Ändern" modal geocodes and repaints.

---

## 11. Parked proposals (explicitly deferred — do NOT build now)

1. **Category-scoped material resolution.** Constrain the Gate-3 Baustoff search to the confirmed
   Bauverfahren's expected material category using the existing `Baustoff.kategorie` (asphalt-laying
   → `Asphaltmischgut`, never `Bindemittel`; aggregate layers → `Gesteinskörnung`; …). This prevents
   the bitumen-for-asphalt category error at the source. The redesign makes it a drop-in (material is
   resolved *after* the BV is confirmed), but it is **out of scope** for this plan. Open question it
   depends on: whether any position legitimately prices a `Bindemittel` on its own (e.g. a tack-coat
   / Anspritzen position per tonne or per litre), which decides global-exclude vs per-recipe category.

2. **Learn the human's correction.** Persist the Gate-2/3/4 human overrides (especially
   Leistung/BV/Baustoff corrections) as a signal so future auto-proposals for similar positions
   improve over time — "the gate fixes it once, the system gets better next time." Connects to the
   Golden-Store persistence decision. **Out of scope** for this plan; noted so it isn't lost.
