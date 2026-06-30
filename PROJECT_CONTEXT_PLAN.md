# Project Context — Global Context Variables (Plan)

Status: **Plan only.** This document is a self-contained implementation plan for adding
**project-scoped "global" context variables** to the EKT calculation flow. It is written to be
loaded into a fresh session with no prior context, so it restates the relevant existing structure.

Companion docs: `LIEFERANTENWAHL_PLAN.md` (supplier selection — already implemented on branch
`lieferanten-wahl`), `LIEFERANTEN_WAHL_STATUS.md` (status + caveats of that work),
`server/shared/services/kalkulation_v2/ARCHITECTURE.md`, `DATA_ARCHITECTURE.md`, `DATA_SCHEMA.md`.

> **This plan builds on, and refactors, the `lieferanten-wahl` branch.** Read §13 (Refactor delta)
> for exactly what moves. In short: the per-position Baustelle handling added there is **promoted to
> the project level** here.

---

## 1. Goal

Today every calculation input is resolved **per LV position**. But many facts are **project-wide**
(the whole Vergabe / road section): where the Baustelle is, where spoil goes, the section's
dimensions, the contamination class. Re-resolving them per position is wasteful and inconsistent.

Introduce a **project context**: a small set of global variables resolved **once per project**
(RAG → user confirmation), **persisted**, and **reused by every LV calculation**, with the option to
**override + save** on any run. A new **pre-Gate-A stage** resolves/presents them before the existing
per-position flow.

### 1.1 The v1 globals (locked with the user)

| Global | Type | Shown / edited as | Stored internally | Feeds |
|---|---|---|---|---|
| `baustelle_location` | location | **address string** | `baustelle_breitengrad`, `baustelle_laengengrad` (geocoded) | supplier ranking (Antransport) |
| `deponie_location` | location | **address string** | `deponie_breitengrad`, `deponie_laengengrad` (geocoded) + `entfernung_deponie_km` (routed Baustelle→Deponie) | Abtransport distance |
| `strip_length_m` | Decimal (m) | number | — | `laenge_m` (default source), `flaeche_m2` bridge |
| `strip_width_m` | Decimal (m) | number | — | `flaeche_m2 = strip_length_m × strip_width_m` |
| `fraesgut_klasse` | int 1–3 | number | — | `fraesgut_klasse` (per-position default) |

**Locations are strings to the user; lat/lon are derived + stored internally on change and never
shown/edited directly** (same contract as the Baustelle in `lieferanten-wahl`).

---

## 2. Decisions locked (with the user)

- **Persistence:** a new **`project_contexts` Postgres table** (one row per project), following the
  repo's Core + repository + UoW pattern. First calc-data persistence in the app.
- **Routing for "heavy tonnage":** **Google car routes for now.** Google's Routes API has **no
  truck/HGV mode** (`DRIVE/BICYCLE/WALK/TWO_WHEELER/TRANSIT` only; `RouteModifiers` can't express
  weight/dimension restrictions), so true heavy-haulage routing is **not possible** with it. We use
  Google `DRIVE` road distances, with a **configurable HGV detour factor** applied as a coarse
  approximation, and **note the HGV gap**. A truck-routing provider (HERE/PTV/OSRM-truck) is deferred.
- **Supplier candidate radius:** a **configurable straight-line (haversine) radius, default 100 km**,
  pre-filters candidates before routing.
- **`strip_*` semantics:** `strip_length_m` sources `laenge_m`; `strip_width_m` + `strip_length_m`
  derive `flaeche_m2`. They are **project defaults**, overridden by per-position booked geometry
  (see §4 precedence and §9 open point).
- **Override + save:** confirming/overriding a global in the pre-Gate-A review **updates the saved
  project value** for all future calculations (shared, not a transient per-calc override).

---

## 3. Precedence model (the core idea)

A global context value is a **new resolution source** sitting between per-position inputs and the
catalog default:

```
per-position input  >  project global  >  catalog KONSTANTE default
(chat / LV menge /     (this feature)      (kontext_variablen mit_default,
 langtext / Gate B)                          stammdaten bridges)
```

Mechanically, the per-position graph injects the project globals as **Gate-B-overridable proposals**
(exactly how `maschinen_werte` / `lieferant_werte` are merged today in `resolve_variables`), so a
position-specific value still wins, and an estimator can still override at Gate B. Booked geometry
(`flaeche_m2`/`volumen_m3`/`laenge_m` filled from the LV `menge`) outranks the `strip_*` globals.

---

## 4. Engine wiring of each global

### 4.1 `baustelle_location` → supplier ranking
The geocoded `baustelle_breitengrad`/`baustelle_laengengrad` drive `rang_lieferanten(...)` (already
built in `server/shared/services/calculator/lieferant_ranking.py`). **No engine variable** — coords
are consumed by the ranker, not by formulas.

### 4.2 `deponie_location` → `entfernung_deponie_km`
Geocode → `deponie_breitengrad`/`deponie_laengengrad`. Then route **Baustelle → Deponie** (Google
`DRIVE`) → `entfernung_deponie_km`. Inject `entfernung_deponie_km` as a resolved value into the
per-position context (replacing today's HITL + 10 km default). This is **symmetric to the supplier
inbound distance** and consumes the `entfernung_lieferant_km` / `entfernung_deponie_km` split already
landed on `lieferanten-wahl` (`formel.py` `trans_boden`/`trans_fraesgut`/`trans_aufbruch`).

### 4.3 `strip_length_m` → `laenge_m` (+ part of `flaeche_m2`)
`laenge_m` is directly referenced by **11 formulas** across the **8 per-metre Leistungen**
(verified against the catalog):

| Leistung (einheit `m`) | formulas |
|---|---|
| L_MARKIERUNG | `markierung_stunden` |
| L_TRENNEN | `schnitt_stunden` |
| L_NAHT | `naht_stunden`, `naht_menge_t` |
| L_NAHT_AUFWEITEN | `naht_aufweiten_stunden` |
| L_FUGENFUELLUNG_N2 | `fugenfuellung_stunden`, `fugen_menge_t` |
| L_RANDABDICHTUNG | `randabdichtung_stunden`, `mk_randabdichtung_material` |
| L_ERSCHWERNIS_* | `lohn_erschwernis` |
| (demarking disposal) | `ent_demark` |

### 4.4 `strip_width_m` (+ `strip_length_m`) → `flaeche_m2`
New bridge `flaeche_m2 = strip_length_m × strip_width_m`. `flaeche_m2` feeds **33 formulas directly /
~90 transitively** (every area-billed Leistung), and `volumen_m3 = flaeche_m2 × schichtdicke_m`. See
§9 for the activation rule (these are defaults; menge-booked geometry wins).

### 4.5 `fraesgut_klasse` → per-position default
Currently a per-position `kontext_variablen` leaf (`RAG → HITL`, `hochrisiko`, no default). As a
global it is resolved once (from the Schadstoff-/PAK-Gutachten) and injected as the per-position
default. Gate B still **surfaces it** (high-stakes) for override.

---

## 5. Data model & persistence

Follow the canonical pattern (copy from the cited files). Naming per `DATA_SCHEMA.md`: snake_case
plural table, `{singular}_uuid` PK, `TIMESTAMPTZ` with server defaults, JSONB for the flexible bag.

### 5.1 Table — `server/shared/db/tables/project_contexts.py` (NEW)
*(copy structure from `server/shared/db/tables/projects.py`; JSONB usage from `tables/messages.py`)*

```python
from sqlalchemy import Column, DateTime, ForeignKey, Table, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata

project_contexts = Table(
    "project_contexts",
    metadata,
    Column("project_context_uuid", UUID(as_uuid=True), primary_key=True,
           server_default=text("gen_random_uuid()")),
    Column("project_uuid", UUID(as_uuid=True),
           ForeignKey("projects.project_uuid", ondelete="CASCADE"),
           nullable=False, unique=True),                 # one context row per project
    # name -> {wert, quelle, beleg, konfidenz, breitengrad?, laengengrad?, status?}
    Column("werte", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    # cross-variable derived values, e.g. {entfernung_deponie_km: "12.4"}
    Column("abgeleitet", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False,
           server_default=func.now(), onupdate=func.now()),
)
```

Register it: add `from shared.db.tables.project_contexts import project_contexts` (and to `__all__`)
in `server/shared/db/tables/__init__.py`. Tables are created by `metadata.create_all` in
`server/scripts/bootstrap_tables.py` on API boot — **no Alembic**; the new table appears
automatically (drop/recreate the dev DB or let `create_all` add it).

### 5.2 JSONB `werte` shape (the contract)
```jsonc
{
  "baustelle_location": {"wert": "L 151 zwischen Blankenheim und Wimmelburg, Landkreis Mansfeld-Südharz",
                          "quelle": "rag", "beleg": "…", "konfidenz": "0.8",
                          "breitengrad": "51.53", "laengengrad": "11.55", "status": "aufgeloest"},
  "deponie_location":   {"wert": "Deponie Sangerhausen", "quelle": "hitl", "beleg": "…",
                          "breitengrad": "51.47", "laengengrad": "11.30", "status": "aufgeloest"},
  "strip_length_m":     {"wert": "5100", "quelle": "rag", "beleg": "Gesamtlänge 5.100 m"},
  "strip_width_m":      {"wert": "1.0",  "quelle": "hitl", "beleg": "Bankettbreite"},
  "fraesgut_klasse":    {"wert": "1",    "quelle": "rag", "beleg": "PAK-Gutachten: unbelastet"}
}
```
`abgeleitet`: `{"entfernung_deponie_km": "12.4"}` (routed Baustelle→Deponie). The `status` field on
locations mirrors the `BAUSTELLE_*` constants already in `state.py`
(`aufgeloest|unsicher|fehlgeschlagen`).

### 5.3 Domain models — `server/shared/models/project_context.py` (NEW)
*(copy from `server/shared/models/project.py`; `ConfigDict(from_attributes=True, extra="forbid")`)*
```python
class ProjectContext(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    project_context_uuid: UUID
    project_uuid: UUID
    werte: dict
    abgeleitet: dict
    created_at: datetime
    updated_at: datetime

class NewProjectContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_uuid: UUID
    werte: dict = Field(default_factory=dict)
    abgeleitet: dict = Field(default_factory=dict)
```

### 5.4 Repository — `server/shared/repositories/project_contexts.py` (NEW)
*(copy from `server/shared/repositories/projects.py`; takes `AsyncConnection`)*
- `async def get(self, project_uuid: UUID) -> ProjectContext | None`
- `async def upsert(self, project_uuid: UUID, werte: dict, abgeleitet: dict) -> ProjectContext`
  (Postgres `insert(...).on_conflict_do_update(index_elements=["project_uuid"], …)`)

Register in `server/shared/db/unit_of_work.py`: `self.project_contexts =
ProjectContextRepository(conn)`.

### 5.5 API schemas — `server/shared/models/project_context_schema.py` (NEW)
The wire shape the UI sees (addresses as strings; coords/distance read-only-derived):
```python
class ProjectContextRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_uuid: UUID
    baustelle_location: str | None
    baustelle_breitengrad: str | None
    baustelle_laengengrad: str | None
    baustelle_status: str | None
    deponie_location: str | None
    deponie_breitengrad: str | None
    deponie_laengengrad: str | None
    deponie_status: str | None
    entfernung_deponie_km: str | None
    strip_length_m: str | None
    strip_width_m: str | None
    fraesgut_klasse: str | None
    # optional provenance per field if the UI wants it
    vorhanden: bool                      # whether a context row exists yet

class ProjectContextUpdate(BaseModel):     # the editable subset (override + save)
    model_config = ConfigDict(extra="forbid")
    baustelle_location: str | None = None
    deponie_location: str | None = None
    strip_length_m: str | None = None
    strip_width_m: str | None = None
    fraesgut_klasse: str | None = None
```
Add both to `server/scripts/export_schema.py` so `npm run gen:types` emits them to
`ui/src/types/generated.ts`.

---

## 6. Global variable registry — `server/shared/services/kalkulation_v2/globale_variablen.py` (NEW)

Reuse the existing `VariableDefinition` model (resolution cascade `RAG → HITL`). Keep a registry +
metadata marking which are **location** globals (string → geocode) and which engine variable each
maps to.

```python
class GlobaleVariable(BaseModel):
    name: str
    bezeichnung: str
    einheit: str | None
    datentyp: Datentyp                 # DEZIMAL / GANZZAHL
    ist_standort: bool = False         # location: string value + geocoded coords
    ziel_variable: str | None = None   # engine variable it sources (e.g. strip_length_m -> "laenge_m")
    rag_prompt: str                    # retrieval intent

GLOBALE_VARIABLEN: dict[str, GlobaleVariable] = {
    "baustelle_location": GlobaleVariable(name="baustelle_location", ist_standort=True,
        rag_prompt="Wo liegt die Baustelle? Ort, Gemeinde, Landkreis und Straße/Straßennummer …", …),
    "deponie_location":  GlobaleVariable(name="deponie_location", ist_standort=True,
        rag_prompt="Welche Deponie/Verwertungsstelle ist vorgesehen? Name/Ort/Adresse …", …),
    "strip_length_m":    GlobaleVariable(name="strip_length_m", ziel_variable="laenge_m",
        rag_prompt="Gesamtlänge des auszubauenden/sanierenden Abschnitts in Metern …", …),
    "strip_width_m":     GlobaleVariable(name="strip_width_m",
        rag_prompt="Breite des Streifens/Banketts/der Fahrbahn in Metern …", …),
    "fraesgut_klasse":   GlobaleVariable(name="fraesgut_klasse",
        rag_prompt="Belastungsklasse des Fräsguts (1 verwertbar / 2 belastet / 3 pechhaltig) …", …),
}
GLOBAL_VAR_NAMES = frozenset(GLOBALE_VARIABLEN)
```

---

## 7. Resolution service — `server/shared/services/project_context/` (NEW)

A small service that resolves, derives, loads, and saves project context. **Separate from the
per-position calc** so it owns its own LLM prompt and never affects the per-position prompt loading.

`service.py`:
- `async def load(conn, project_uuid) -> ProjectContextRead | None` — read the row, project the
  JSONB into the flat schema.
- `async def resolve(project_uuid, retriever, llm, prompt, maps) -> dict` — for each global not yet
  set: RAG-retrieve (via `RetrievalService.retrieve_context(question, project_uuid, CONFIG)`), then
  LLM-extract the value (§7.1). For location globals, **geocode** the extracted string →
  coords/status. Then **derive** `entfernung_deponie_km = maps.road_distance_km(baustelle, deponie)`.
- `async def save(engine, project_uuid, update: ProjectContextUpdate, maps) -> ProjectContextRead` —
  merge edits; **geocode any changed location** (string → coords; never accept coords from the UI);
  **recompute** `entfernung_deponie_km` when either location changed; `upsert` via the repo.

Retrieval config: reuse the calculator's policy
(`CALCULATOR_RETRIEVAL_CONFIG` in `graph.py` — `PLUS`, multi-query, BM25, cross-encoder).

Maps client: reuse `server/shared/clients/maps/geo.py` (`geocode`, `road_distance_km`) from
`lieferanten-wahl`.

### 7.1 LLM extraction prompt (NEW PromptType)
Add `EKT_PROJEKT_KONTEXT = "ekt_projekt_kontext"` to `PromptType`
(`server/shared/models/enums.py`). Create seed file
`server/scripts/seed/prompts/ekt_projekt_kontext.prompt` (frontmatter `model_name`/`temperature` +
system prompt). Add a `llm_calls`-style function returning a structured extraction:
```python
class ProjektKontextExtraktion(BaseModel):
    reasoning: list[str] = []
    baustelle_location: str | None
    deponie_location: str | None
    strip_length_m: str | None
    strip_width_m: str | None
    fraesgut_klasse: str | None
    # per-field confidence + beleg optional
```
The chat screenshot proved the project's RAG+LLM finds the location cleanly
("L 151 between Blankenheim and Wimmelburg, Landkreis Mansfeld-Südharz"), so this **replaces the weak
raw-chunk geocoding** currently in `locate_baustelle`.

**Load it independently** of `load_calculator_prompts` (so an unseeded prompt can't break per-position
calc). Seeding step: `python -m scripts.seed.prompts` (appends a version). Mock mode: the resolver
returns fixtures (baustelle `51.42,10.81`; a deponie fixture; `strip_length_m=5100`,
`strip_width_m=1.0`, `fraesgut_klasse=1`) so the offline flow runs.

---

## 8. Graph integration — `server/shared/services/calculator/graph.py`

### 8.1 New topology (per LV calculation run)
```
launch
  -> load_project_context     (NEW: load saved context; if missing/incomplete, RESOLVE via §7)
  -> project_context_review   (NEW interrupt — the "pre-Gate-A" gate: confirm/override + SAVE)
  -> extract_chat_values
  -> classify_leistung
  -> rank_lieferanten         (NEW node, formerly part of locate_baustelle: rank suppliers for the
                               proposed Baustoff using the CONFIRMED project baustelle coords)
  -> method_review            (Gate A: supplier picker stays; Baustelle field REMOVED — now project-level)
  -> bind_resources
  -> bind_lieferant           (uses project baustelle coords; honour Gate A supplier pick)
  -> derive_required_variables
  -> resolve_variables        (merge project globals as Gate-B-overridable sources, §3)
  -> variable_review          (Gate B)
  -> compute                  (inject entfernung_deponie_km + strip-derived geometry; price override)
  -> render_output
```

### 8.2 `load_project_context` node
- Load via the repo (`ProjectContextRepository(conn).get(project_uuid)`).
- If a global is missing, call the resolver (§7). Mock mode → fixtures.
- Write the flat context into state (`projekt_kontext`), including derived coords + `entfernung_deponie_km`.
- Does **not** itself persist (the review node saves after user confirmation).

### 8.3 `project_context_review` interrupt (the pre-Gate-A gate)
- Payload (`stage = "project_context_review"`): the 5 globals — **locations as strings** + their
  status, the three numbers, plus the derived `entfernung_deponie_km` (read-only display).
- Answer: edited address strings + numbers (an `update` dict shaped like `ProjectContextUpdate`).
- On submit: **geocode changed locations**, **recompute `entfernung_deponie_km`**, **SAVE** to
  `project_contexts` (via the engine + repo `upsert`, mirroring `run_service._capture_gate_b`'s short
  transaction), update `projekt_kontext` in state. Then continue.
- If a location is `fehlgeschlagen`, the field is empty for manual entry (same UX as the
  `lieferanten-wahl` manual fallback).

### 8.4 Per-position injection (precedence, §3)
- **Supplier ranking** (`rank_lieferanten`, `bind_lieferant`): use
  `projekt_kontext.baustelle_breitengrad/laengengrad`.
- **`entfernung_deponie_km`**: inject as a resolved `VariablenWert`
  (`quelle=STAMMDATEN`, `beleg="Baustelle → Deponie X, N km (Google Routes)"`) — like
  `lieferant_werte` is injected today. Gate B overridable.
- **`fraesgut_klasse`**: inject the project value as the per-position default (Gate B still surfaces).
- **`strip_length_m`/`strip_width_m`**: compute strip-derived `laenge_m` and
  `flaeche_m2 = strip_length_m × strip_width_m` and inject **only when the position does not book that
  geometry from `menge`** (§9). All injected via the existing `gebundene_werte` merge in
  `resolve_variables` so they show collapsed and overridable at Gate B.

---

## 9. Geometry activation rule (open design point — decide during impl)

Most positions book geometry from the LV `menge` (`geom = GEOM[einheit]`, pruned from the worklist),
so `strip_*` rarely overrides. The recommended rule:

> Inject a `strip_*`-derived value for `laenge_m` / `flaeche_m2` **only when that variable is in the
> worklist (i.e. the recipe needs it) AND the position did not book it from `menge`.** Booked menge
> geometry always wins; `strip_*` is the fallback/default below it.

This needs validation against real LV positions (which positions actually rely on the strip dims vs.
their own `menge`). Capture the decision with the user once we can run against a real Vergabe. Until
then, wire the injection but gate it behind "variable needed ∧ not booked," and expose both strip
globals at Gate B so an estimator can always see/override.

---

## 10. Supplier ranking changes — `lieferant_ranking.py` + `config.py`

- Add `calculator_lieferant_radius_km: float = 100.0` to `Settings`. In `rang_lieferanten`, **filter
  carriers to within the haversine radius** before route-matrixing (replaces/augments `top_n`).
- Add `calculator_hgv_detour_factor: float = 1.0` (1.0 = off). Multiply the routed road distance by
  it as a coarse HGV approximation; document that Google can't do true truck routing.
- `route_matrix` stays Google `DRIVE`; the existing per-pair haversine fallback remains.

---

## 11. API — `server/api/routes/project_contexts.py` (NEW)
*(copy patterns from `server/api/routes/projects.py`; deps from `server/api/deps.py`)*
- `GET  /projects/{project_uuid}/context` → `ProjectContextRead` (read-only conn). 404 → `vorhanden=false`
  body (or 200 with nulls) so the UI can show "not yet resolved."
- `PUT  /projects/{project_uuid}/context` → `ProjectContextUpdate` → save (UoW) → `ProjectContextRead`.
- `POST /projects/{project_uuid}/context/resolve` → trigger RAG resolution (UoW + retriever/llm/maps)
  → `ProjectContextRead` (optional; the calc flow also resolves lazily).

Register the router in `server/api/main.py` (`app.include_router(project_contexts.router)`).

---

## 12. UI

### 12.1 Pre-Gate-A review (primary) — `ui/src/views/workspace/InterruptPanel.tsx`
- New stage constant `STAGE_PROJECT_CONTEXT_REVIEW = "project_context_review"` + a `ProjectContextReview`
  component dispatched alongside `MethodReview`/`VariableReview`.
- Renders: **two address inputs** (Baustelle, Deponie) with status badges (reuse the `BAUSTELLE_*`
  badge styling already added on `lieferanten-wahl`), three number inputs (strip length/width,
  fräsgut class), and the derived `entfernung_deponie_km` read-only. Submit posts an `update` in the
  resume (`CalculationResume` gains a `projekt_kontext?` field).
- **Remove** the per-position Baustelle field from `MethodReview` (added on `lieferanten-wahl`) — it
  now lives here. Keep the supplier picker in `MethodReview`.

### 12.2 Project-level panel (optional/secondary) — `ui/src/views/main/ProjectContextPanel.tsx` (NEW)
*(hooks from `ui/src/api/project-context.ts` NEW, copy `ui/src/api/projects.ts` pattern;
mount in `ui/src/views/main/ProjectDetails.tsx` as a tab/section)* — lets the user edit project
context outside a calc run (`useProjectContext` / `useUpdateProjectContext`).

### 12.3 Types
After the API schema lands and `export_schema.py` is updated, run `npm run gen:types` to emit
`ProjectContextRead` / `ProjectContextUpdate` into `ui/src/types/generated.ts` (never hand-edit it).

---

## 13. Refactor delta from `lieferanten-wahl` (what moves)

The `lieferanten-wahl` branch put the Baustelle at the **position** level. This plan **promotes it to
the project** level. Concretely:

- **`graph.py`:** delete `locate_baustelle`'s geocoding + the per-position `baustelle_*` state writes;
  split its supplier-ranking into the new `rank_lieferanten` node (post-classify). `bind_lieferant`
  reads coords from `projekt_kontext`, not per-position state. `compute` injects
  `entfernung_deponie_km` from project context (instead of relying on the 10 km HITL default).
- **`state.py`:** the per-position `baustelle_breitengrad/laengengrad/adresse/status/override` fields
  are **superseded** by a single `projekt_kontext: dict` (loaded once) + the saved row. Keep the
  `BAUSTELLE_*` status constants (reused). `lieferanten_vorschlag`/`gewaehlter_lieferant`/
  `lieferant_*` stay as-is.
- **`InterruptPanel.tsx`:** remove the Baustelle field from `MethodReview` (§12.1); the supplier
  picker stays. Remove `baustelle` from the Gate-A `CalculationResume` (moves to `projekt_kontext`).
- **`kontext_variablen.py`:** the `entfernung_deponie_km` default stays as a last-resort fallback;
  `fraesgut_klasse` keeps its per-position definition (now also fed by the project default). The
  Baustelle coordinate `koordinate()` vars added there can be **removed** (coords are project-level
  now, not engine variables) — confirm nothing else references them.
- Keep everything else from `lieferanten-wahl` (the `entfernung_km` split, `formel.py` rewiring,
  `lieferant_ranking.py`, `maps/geo.py`, `lade_preise` in `store.py`).

---

## 14. Config / settings (`server/shared/config.py`)
- `calculator_lieferant_radius_km: float = 100.0`
- `calculator_hgv_detour_factor: float = 1.0`
- (existing, reused) `google_static_maps_api_key`, `google_maps_geocoding_url`,
  `google_maps_route_matrix_url`, `maps_request_timeout_seconds`, `calculator_mock`.

---

## 15. Tests / eval
- **Unit (engine, pydantic-only):** `globale_variablen` registry shape; the `strip_length_m → laenge_m`
  and `flaeche_m2 = strip_length_m × strip_width_m` derivations; the precedence (position menge beats
  strip global; project global beats catalog default).
- **Unit (service, mock):** `project_context` resolver with mock geocode/route + a stubbed extractor
  (fixtures); `save` geocodes a changed address and recomputes `entfernung_deponie_km`; repo `upsert`.
- **Unit (graph, mock):** `project_context_review` interrupt surfaces the 5 globals; an override saves
  and flows into the per-position calc (e.g. `entfernung_deponie_km` reflects the routed Baustelle→
  Deponie; supplier ranking uses the project baustelle).
- **Integration:** full run on a fixture position with a pre-existing project context → supplier-driven
  Material + Antransport and deponie-driven Abtransport.
- **Repository integration:** `project_contexts` upsert/get round-trip (test DB).

> Sandbox note (from `LIEFERANTEN_WAHL_STATUS.md`): the build env may lack `uv`/`pytest`/
> `pydantic_settings` and a populated `ui/node_modules`; only the pure `kalkulation_v2` engine runs
> there. Validate with `uv run pytest` + `npm install && npm run build` in a real env.

---

## 16. Touched files (checklist)

**New**
- `server/shared/db/tables/project_contexts.py`
- `server/shared/models/project_context.py`
- `server/shared/models/project_context_schema.py`
- `server/shared/repositories/project_contexts.py`
- `server/shared/services/kalkulation_v2/globale_variablen.py`
- `server/shared/services/project_context/__init__.py`, `service.py`, (extraction) `llm_calls.py`
- `server/scripts/seed/prompts/ekt_projekt_kontext.prompt`
- `server/api/routes/project_contexts.py`
- `ui/src/api/project-context.ts`
- `ui/src/views/main/ProjectContextPanel.tsx` (optional)
- tests under `tests/unit/**` and `tests/integration/**`

**Modified**
- `server/shared/db/tables/__init__.py` (register table)
- `server/shared/db/unit_of_work.py` (register repo)
- `server/shared/models/enums.py` (`PromptType.EKT_PROJEKT_KONTEXT`)
- `server/scripts/export_schema.py` (export the two schemas)
- `server/api/main.py` (include router)
- `server/shared/config.py` (radius + HGV factor)
- `server/shared/services/calculator/graph.py` (topology; load + review nodes; rank split;
  injection; remove per-position baustelle)
- `server/shared/services/calculator/state.py` (`projekt_kontext`; drop per-position baustelle fields)
- `server/shared/services/calculator/run_service.py` (capture/save project-context review, mirroring
  `_capture_gate_b`)
- `server/shared/services/calculator/lieferant_ranking.py` (radius + HGV factor)
- `server/shared/services/kalkulation_v2/kontext_variablen.py` (remove Baustelle coord vars; keep
  `entfernung_deponie_km` fallback)
- `ui/src/views/workspace/InterruptPanel.tsx` (new review stage; remove per-position baustelle field)
- `ui/src/api/calculations.ts` (`CalculationResume.projekt_kontext`)
- `ui/src/views/main/ProjectDetails.tsx` (mount the optional panel)

**Canonical source files to copy from** (verified):
`tables/projects.py`, `tables/messages.py` (JSONB), `models/project.py`, `models/project_schema.py`,
`repositories/projects.py`, `db/unit_of_work.py`, `api/deps.py`, `api/routes/projects.py`,
`services/retrieval/service.py` (`retrieve_context`), `scripts/bootstrap_tables.py`,
`scripts/export_schema.py`, `scripts/seed/prompts/`, `ui/src/api/projects.ts`,
`ui/src/views/main/ProjectDetails.tsx`.

---

## 17. Implementation order (phased)

1. **Persistence skeleton** — table + model + schema + repo + UoW + bootstrap; a repo round-trip test.
2. **Registry + resolver** — `globale_variablen`, `project_context` service (RAG extract + geocode +
   route), the new `PromptType` + seed file, mock fixtures; service unit tests.
3. **API + UI panel** — endpoints + `export_schema` + `gen:types` + `ProjectContextPanel`
   (lets you resolve/save context standalone, decoupled from the calc graph — good for early testing).
4. **Graph integration** — `load_project_context` + `project_context_review` interrupt; refactor
   `locate_baustelle` → `rank_lieferanten`; per-position injection (entfernung_deponie_km, fraesgut,
   strip geometry); `run_service` save; mock graph tests.
5. **Geometry + radius/HGV** — strip bridges with the §9 activation rule; ranker radius + HGV factor.
6. **Cleanup** — remove the per-position Baustelle remnants (§13); update
   `LIEFERANTEN_WAHL_STATUS.md` / write a `PROJECT_CONTEXT_STATUS.md`.

---

## 18. Open questions / risks / deferred

- **§9 geometry activation** — exactly which positions consume `strip_*` vs. their own `menge`. Decide
  with real LV data.
- **HGV routing** — Google can't do truck routing; the detour factor is a stopgap. Revisit a
  truck-routing provider if haul accuracy matters for bids.
- **Resolution trigger** — resolve lazily on the first calc (planned) vs. eagerly at project
  creation/ingestion. Lazy is the v1 default; eager is a later optimization.
- **Per-calc transient override** — currently override **saves** to the project. If a one-off per-calc
  override (without mutating the project) is ever needed, add a "don't save" toggle.
- **Multi-section projects** — one context row per project assumes one Baustelle/section. A project
  spanning several sections would need context keyed below project level (deferred).
- **Stichtag / price coverage** — unchanged from `lieferanten-wahl` (supplier prices load at
  `gueltig_ab = 2026-01-01`; calc `STICHTAG = 2026-06-22`).
