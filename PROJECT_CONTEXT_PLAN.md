# Project Context — Global Context Variables (Plan)

Status: **Plan only.** Self-contained implementation plan for **project-scoped "global" context
variables** in the EKT calculation flow. Written to be loaded into a fresh session cold.

Companion docs: `LIEFERANTENWAHL_PLAN.md` + `LIEFERANTEN_WAHL_STATUS.md` (supplier selection — already
implemented on branch `lieferanten-wahl`), `server/shared/services/kalkulation_v2/ARCHITECTURE.md`,
`DATA_ARCHITECTURE.md`, `DATA_SCHEMA.md`.

> **This builds on, and refactors, the `lieferanten-wahl` branch.** See §13 — the per-position
> Baustelle handling added there is **promoted to the project level** here.

---

## 1. Goal

Many inputs are **project-wide** (the whole Vergabe / road section): where the Baustelle is, where
spoil goes, the section's dimensions, the contamination class. Re-resolving them per LV position is
wasteful and inconsistent.

Introduce a **project context**: a small set of global variables resolved **once per project**
(RAG → user confirmation), **persisted with per-variable version history**, and **reused by every LV
calculation**, with **override + save** on any run. A new **pre-Gate-A stage** resolves/reconciles/
presents them before the existing per-position flow.

### 1.1 The v1 globals (locked)

| Global | Type | Shown / edited as | Stored internally (versioned with the value) | Feeds |
|---|---|---|---|---|
| `baustelle_location` | location | **address string** | `baustelle_breitengrad`, `baustelle_laengengrad` | supplier ranking (Antransport) |
| `deponie_location` | location | **address string** | `deponie_breitengrad`, `deponie_laengengrad` | Abtransport distance |
| `strip_length_m` | Decimal (m) | number | — | `laenge_m` (fallback source), `flaeche_m2` bridge |
| `strip_width_m` | Decimal (m) | number | — | `flaeche_m2 = strip_length_m × strip_width_m` |
| `fraesgut_klasse` | int 1–3 | number | — | `fraesgut_klasse` (per-position default) |

Plus one **derived, governed** variable: `entfernung_deponie_km` (routed Baustelle→Deponie;
`quelle=routing`). Locations are strings to the user; lat/lon are derived + stored internally on
change and never shown/edited directly.

---

## 2. Decisions locked (with the user)

- **Persistence = per-variable version history (SCD-2).** A `project_context_values` table, **one row
  per `(project, variable, version)`**; an override **closes out the current row** (`gueltig_bis`,
  `ist_aktuell=false`) and **inserts the new version** — a version's value/source are never altered.
  Point-in-time supported. Full value-source provenance per version (§5).
- **Resolution = hybrid RAG + a dedicated synthesis prompt.** `retrieve_context` (BM25 + dense +
  cross-encoder) *finds* the chunks; a **dedicated** `PROJECT_CONTEXT_RESOLVE` structured-output prompt
  distills them into the value + provenance — **one focused retrieval + extraction per variable** (no
  single multi-variable pass: avoids context rot / cross-variable pollution and keeps each retrieval
  tightly scoped). Locations then geocoded (§7). **Not** the LV-Langtext extractor
  (`EKT_LANGTEXT_EXTRACT`) — that's per-position Langtext.
- **Routing = Google car routes** (Routes API has **no truck/HGV mode**), + a configurable haversine
  candidate radius (default 100 km) + a configurable HGV detour factor. True truck routing deferred.
- **Supplier radius is a soft filter:** if **no** carrier is within the radius, fall back to the
  single nearest and emit a **WARNING** into the reasoning output (§10).
- **Topology: chat first.** `extract_chat_values` runs first and also extracts global candidates; the
  pre-Gate-A gate reconciles chat vs. saved vs. RAG and offers **Confirm / Override / Conflict** per
  variable (§8).
- **Geometry: provided wins.** Booked per-position geometry (`menge`) always wins; `strip_*` derive
  geometry only as a **fallback** (§9).
- **Override + save** appends a new version (shared project value), not a transient per-calc override.
- **Reasoning UX:** show only the latest reasoning line, expandable to the full history, + a prominent
  activity indicator while streaming (§12.4).

---

## 3. Precedence model (the core idea)

A global value is a **resolution source** between per-position inputs and the catalog default:

```
per-position input  >  project global  >  catalog KONSTANTE default
```

Mechanically, the per-position graph injects the project globals as **Gate-B-overridable proposals**
(exactly how `maschinen_werte` / `lieferant_werte` are merged today in `resolve_variables`), so a
position-specific value still wins and the estimator can override at Gate B. Booked geometry
(`menge`) outranks the `strip_*` globals (§9).

---

## 4. Engine wiring of each global

- **`baustelle_location`** → geocoded coords drive `rang_lieferanten(...)`
  (`server/shared/services/calculator/lieferant_ranking.py`). No engine variable.
- **`deponie_location`** → geocoded coords; route **Baustelle → Deponie** (Google `DRIVE`) →
  `entfernung_deponie_km`, injected per position (replaces the HITL + 10 km default). Consumes the
  `entfernung_lieferant_km`/`entfernung_deponie_km` split already on `lieferanten-wahl`.
- **`strip_length_m`** → `laenge_m` (11 formulas / 8 per-metre Leistungen: L_MARKIERUNG, L_TRENNEN,
  L_NAHT, L_NAHT_AUFWEITEN, L_FUGENFUELLUNG_N2, L_RANDABDICHTUNG, L_ERSCHWERNIS_*, `ent_demark`).
- **`strip_width_m`** (+ `strip_length_m`) → bridge `flaeche_m2 = strip_length_m × strip_width_m`
  (`flaeche_m2`: 33 formulas direct / ~90 transitive; then `volumen_m3 = flaeche_m2 × schichtdicke_m`).
- **`fraesgut_klasse`** → injected as the per-position default; Gate B still surfaces it (high-stakes).

---

## 5. Data model & persistence (per-variable version history)

Follow the Core + repository + UoW pattern (`DATA_ARCHITECTURE.md`). Naming per `DATA_SCHEMA.md`.

### 5.1 Table — `server/shared/db/tables/project_context_values.py` (NEW)
*(copy structure from `tables/lv_items.py`; JSONB from `tables/messages.py`)*
```python
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, Table,
                        Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from shared.db.metadata import metadata

project_context_values = Table(
    "project_context_values",
    metadata,
    Column("project_context_value_uuid", UUID(as_uuid=True), primary_key=True,
           server_default=text("gen_random_uuid()")),
    Column("project_uuid", UUID(as_uuid=True),
           ForeignKey("projects.project_uuid", ondelete="CASCADE"), nullable=False, index=True),
    Column("variable_name", Text, nullable=False),       # e.g. "baustelle_location"
    Column("version", Integer, nullable=False),          # 1,2,3… per (project, variable)
    Column("wert", Text, nullable=False),                # user-facing value (address string or number)
    Column("breitengrad", Text, nullable=True),          # derived coords (location vars only)
    Column("laengengrad", Text, nullable=True),
    Column("quelle", Text, nullable=False),              # ContextQuelle: rag | hitl | routing
    Column("beleg", Text, nullable=True),                # literal evidence quote
    Column("quelle_referenz", JSONB, nullable=True),     # structured source (see 5.2)
    Column("konfidenz", Numeric, nullable=True),
    Column("benutzer", Text, nullable=True),             # HITL override user (denormalized for filter)
    Column("status", Text, nullable=True),               # location: aufgeloest|unsicher|fehlgeschlagen
    Column("ist_aktuell", Boolean, nullable=False, server_default=text("true")),
    Column("gueltig_ab", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("gueltig_bis", DateTime(timezone=True), nullable=True),   # set on supersede (SCD-2)
    Column("erstellt_am", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("project_uuid", "variable_name", "version"),
    Index("uq_pcv_aktuell", "project_uuid", "variable_name", unique=True,
          postgresql_where=text("ist_aktuell")),          # exactly one current row per variable
)
```
**SCD-2:** on a change, **close out** the current row (`gueltig_bis = now`, `ist_aktuell = false`) and
**insert** the new version (`ist_aktuell = true`, new `gueltig_ab`, `version+1`). A version's
value/source are never altered. **Current** = `WHERE ist_aktuell`; **point-in-time** =
`WHERE gueltig_ab <= T AND (gueltig_bis IS NULL OR gueltig_bis > T)`. The partial unique index keeps
exactly one current row per variable.

Register: `tables/__init__.py` (import + `__all__`). Created by `metadata.create_all` in
`scripts/bootstrap_tables.py` on boot (no Alembic).

### 5.2 `quelle_referenz` shape (governance value source)
- **rag:** `{"retrieval": {modality, multi_query, use_bm25, use_cross_encoder, top_k},
  "treffer": [{"document_uuid": "...", "seite": 12, "chunk_uuid": "...", "score": 0.81}]}`
- **hitl:** `{"benutzer": "arthur@…"}` (also in the `benutzer` column)
- **routing:** `{"provider": "google_routes", "von": "baustelle_location@v3", "nach": "deponie_location@v2"}`

### 5.3 Domain models — `server/shared/models/project_context.py` (NEW)
```python
class ContextQuelle(StrEnum):
    RAG = "rag"; HITL = "hitl"; ROUTING = "routing"

class ProjectContextValue(BaseModel):           # one version
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    project_context_value_uuid: UUID
    project_uuid: UUID
    variable_name: str
    version: int
    wert: str
    breitengrad: str | None = None
    laengengrad: str | None = None
    quelle: ContextQuelle
    beleg: str | None = None
    quelle_referenz: dict | None = None
    konfidenz: Decimal | None = None
    benutzer: str | None = None
    status: str | None = None
    ist_aktuell: bool
    gueltig_ab: datetime
    gueltig_bis: datetime | None = None
    erstellt_am: datetime

class NewProjectContextValue(BaseModel):        # insert; repo computes `version` + closes out prior
    model_config = ConfigDict(extra="forbid")
    project_uuid: UUID
    variable_name: str
    wert: str
    breitengrad: str | None = None
    laengengrad: str | None = None
    quelle: ContextQuelle
    beleg: str | None = None
    quelle_referenz: dict | None = None
    konfidenz: Decimal | None = None
    benutzer: str | None = None
    status: str | None = None
```

### 5.4 Repository — `server/shared/repositories/project_context_values.py` (NEW)
```python
async def current(self, project_uuid: UUID) -> dict[str, ProjectContextValue]:
    # WHERE project_uuid = … AND ist_aktuell  -> {variable_name: value}
async def history(self, project_uuid: UUID, variable_name: str) -> list[ProjectContextValue]:
    # all versions, ascending by version
async def as_of(self, project_uuid: UUID, zeitpunkt: datetime) -> dict[str, ProjectContextValue]:
    # point-in-time: gueltig_ab <= zeitpunkt AND (gueltig_bis IS NULL OR gueltig_bis > zeitpunkt)
async def supersede(self, new: NewProjectContextValue) -> ProjectContextValue:
    # SCD-2 write (inside the UoW txn): UPDATE the current row SET gueltig_bis=now(), ist_aktuell=false;
    # INSERT version = prior+1, ist_aktuell=true. UNIQUE(project,variable,version) + the partial unique
    # index guard races.
```
Register in `db/unit_of_work.py`: `self.project_context_values = ProjectContextValueRepository(conn)`.

### 5.5 API schemas — `server/shared/models/project_context_schema.py` (NEW)
The flat **current** view (the calc/UI consume this; addresses as strings, coords/distance derived):
```python
class ProjectContextRead(BaseModel):           # projection of current() across variables
    model_config = ConfigDict(extra="forbid")
    project_uuid: UUID
    vorhanden: bool                            # any version exists yet
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

class ProjectContextUpdate(BaseModel):         # editable subset (override -> appends versions)
    model_config = ConfigDict(extra="forbid")
    baustelle_location: str | None = None
    deponie_location: str | None = None
    strip_length_m: str | None = None
    strip_width_m: str | None = None
    fraesgut_klasse: str | None = None

class ProjectContextHistory(BaseModel):        # governance view
    variable_name: str
    versionen: list[ProjectContextValue]
```
Export all in `scripts/export_schema.py` → `npm run gen:types`.

---

## 6. Global variable registry — `server/shared/services/kalkulation_v2/globale_variablen.py` (NEW)

```python
class GlobaleVariable(BaseModel):
    name: str
    bezeichnung: str
    einheit: str | None
    datentyp: Datentyp                 # DEZIMAL / GANZZAHL
    ist_standort: bool = False         # location: string value + geocoded coords
    ziel_variable: str | None = None   # engine variable it sources (strip_length_m -> "laenge_m")
    rag_prompt: str                    # retrieval intent for retrieve_context

GLOBALE_VARIABLEN: dict[str, GlobaleVariable] = { baustelle_location, deponie_location,
    strip_length_m (ziel="laenge_m"), strip_width_m, fraesgut_klasse }
GLOBAL_VAR_NAMES = frozenset(GLOBALE_VARIABLEN)
```
`entfernung_deponie_km` is a **derived** governed variable (computed, not in this registry).

---

## 7. Resolution service — `server/shared/services/project_context/` (NEW)

Reuses existing infra; **no new prompt**.

- `async def resolve(project_uuid, retrieval: RetrievalService, llm, resolve_prompt, maps)` — for each
  global not yet present:
  1. `ctx = await retrieval.retrieve_context(GLOBALE_VARIABLEN[name].rag_prompt, project_uuid, CONFIG)`
     — the **hybrid BM25 + dense + cross-encoder** retrieval; **called directly** (not the calc graph's
     text-only `retrieve`) to keep chunk provenance (`document_uuid`, `seite`, `chunk_uuid`, `score`).
     `CONFIG` = the calculator policy (`PLUS`, multi-query, BM25, cross-encoder).
  2. `ext = await project_context_llm.resolve_globale(llm, name, GLOBALE_VARIABLEN[name],
     [c.chunk_text for c in ctx.context], prompt=resolve_prompt)` — a **dedicated** structured-output
     synthesis (the new `PROJECT_CONTEXT_RESOLVE` prompt, §7.1) returning `{wert, konfidenz, beleg}`.
  3. For location globals: `geocode(ext.wert)` → coords + `status` (reuse `clients/maps/geo.py`).
  4. Build a `NewProjectContextValue` with `quelle=RAG`, `quelle_referenz={retrieval, treffer}`,
     `beleg=ext.beleg`, `konfidenz`.
  - Then derive `entfernung_deponie_km = maps.road_distance_km(baustelle, deponie)` (`quelle=ROUTING`).
- `async def save(uow, project_uuid, update: ProjectContextUpdate, benutzer, maps)` — for each changed
  field: **geocode changed locations** (string→coords; never accept coords from the UI), **recompute**
  `entfernung_deponie_km` if either location changed, and `supersede` per changed variable (SCD-2 new
  version, `quelle=HITL`, `benutzer`).
- `async def current_read(conn, project_uuid) -> ProjectContextRead` — project `repo.current()`.

> **Why a synthesis step:** the hybrid RAG *finds* the right chunks but returns *chunks, not values* —
> geocoding a raw chunk fails (observed). The clean location string in the project-chat screenshot is
> the chat's LLM *synthesizing* over those chunks. So we keep the hybrid retrieval for finding and add a
> **dedicated** synthesis prompt (purpose-built for the globals, structured output for governance) —
> distinct from the per-position `EKT_LANGTEXT_EXTRACT` (wrong domain) and lighter than the full
> conversational chat agent. Zero-LLM (geocode-the-top-chunk) is the unreliable path we already hit.

### 7.1 The dedicated resolution prompt (NEW)
Add `PROJECT_CONTEXT_RESOLVE = "project_context_resolve"` to `PromptType`
(`server/shared/models/enums.py`) + seed file `scripts/seed/prompts/project_context_resolve.prompt` +
a `services/project_context/llm.py` site `resolve_globale(...)` returning a structured
`{wert, konfidenz, beleg}` (reasoning-augmented). **One variable per call** — `resolve_globale` resolves
exactly ONE global from a retrieval focused on that variable's `rag_prompt`. The loop in §7 calls it
once per global; there is deliberately **no** single multi-variable pass (it would mix unrelated chunks
and invite cross-variable hallucination / context rot). The structured output is therefore a single
`{wert, konfidenz, beleg}`, never a bag of all five. Load the prompt **independently** of
`load_calculator_prompts` (an unseeded prompt must not break per-position calc). Seed once:
`python -m scripts.seed.prompts`.

Mock mode (`settings.calculator_mock`): return fixtures (baustelle `51.42,10.81`; a deponie fixture;
`strip_length_m=5100`, `strip_width_m=1.0`, `fraesgut_klasse=1`) so the offline flow runs.

---

## 8. Graph integration — `server/shared/services/calculator/graph.py`

### 8.1 New topology
```
launch
  -> extract_chat_values      (FIRST; now also extracts GLOBAL candidates, not just per-position)
  -> load_project_context     (NEW: current() from repo; resolve missing via §7; RECONCILE with chat candidates)
  -> project_context_review   (NEW interrupt — pre-Gate-A: Confirm / Override / Conflict per variable; SAVE appends versions)
  -> classify_leistung
  -> rank_lieferanten         (NEW node, split from old locate_baustelle: rank suppliers for the proposed Baustoff using the CONFIRMED project baustelle coords)
  -> method_review            (Gate A: supplier picker stays; Baustelle field REMOVED — now project-level)
  -> bind_resources -> bind_lieferant
  -> derive_required_variables -> resolve_variables   (merge project globals as Gate-B-overridable sources, §3)
  -> variable_review (Gate B)
  -> compute (inject entfernung_deponie_km + strip-derived geometry fallback; supplier price override)
  -> render_output
```

### 8.2 `extract_chat_values` (extended)
Add the **global** catalog (`GLOBALE_VARIABLEN`) to the chat-extraction targets, so values the user
already stated in chat (e.g. "the deponie is in Sangerhausen", "the section is 5.1 km") are captured
as global candidates, tagged source = chat/HITL.

### 8.3 `load_project_context` (reconcile)
- `repo.current(project_uuid)` → saved values. For any missing global, run §7 resolve. Mock → fixtures.
- **Reconcile** with the chat candidates from 8.2: per variable, compute one of
  `bestaetigen` (no saved value / chat agrees) · `ueberschreiben` (chat proposes, none saved) ·
  `konflikt` (chat value ≠ saved value). Stash `projekt_kontext` (current flat view) + the
  per-variable reconcile state into graph state.

### 8.4 `project_context_review` interrupt (3-way gate)
- Payload (`stage = "project_context_review"`): per global — current value (locations as **strings**)
  + status, the chat candidate (if any), and the reconcile flag (`bestaetigen|ueberschreiben|konflikt`);
  plus derived `entfernung_deponie_km` (read-only).
- Answer per variable: **Confirm** (keep current), **Override** (new value), or resolve a **Conflict**
  (pick chat vs. saved or type a new one).
- On submit: `ProjectContextService.save(...)` — geocode changed locations, recompute deponie distance,
  **supersede** per changed variable (SCD-2 new version, `quelle=HITL`, `benutzer` = the placeholder
  user for now, §11.1). Update `projekt_kontext` in state; continue.

### 8.5 Per-position injection (precedence §3)
- supplier ranking ← `projekt_kontext` baustelle coords.
- `entfernung_deponie_km` injected as a resolved `VariablenWert` (`quelle=STAMMDATEN`,
  `beleg="Baustelle → Deponie X, N km (Google Routes)"`), Gate-B overridable.
- `fraesgut_klasse` injected as the per-position default.
- `strip_*` → `laenge_m` / `flaeche_m2` injected **only as fallback** (§9), via the existing
  `gebundene_werte` merge in `resolve_variables`.

---

## 9. Geometry activation (DECIDED)

**Provided geometry wins; strip dims are the fallback.** If the position books the needed geometry
from the LV `menge` (`geom = GEOM[einheit]`, pruned from the worklist), use it. Otherwise, if the
recipe needs `laenge_m`/`flaeche_m2` and the strip globals are set, compute
`laenge_m = strip_length_m` and `flaeche_m2 = strip_length_m × strip_width_m` (then
`volumen_m3 = flaeche_m2 × schichtdicke_m`) and inject as a Gate-B-overridable fallback.

---

## 10. Supplier ranking — `lieferant_ranking.py` + `config.py`

- `calculator_lieferant_radius_km: float = 100.0` — in `rang_lieferanten`, filter carriers to within
  this haversine radius before route-matrixing.
- **No-supplier-in-radius fallback:** if the radius filter is empty, take the **single nearest carrier
  regardless of distance** and return a `warnung` so the graph emits a **WARNING** into the reasoning
  output (`reason(...)` + the `warnungen` channel): e.g. *"Kein Lieferant innerhalb 100 km für {bc} —
  nächster ist {name} ({km} km)."*
- `calculator_hgv_detour_factor: float = 1.0` — multiply Google `DRIVE` distance as a coarse HGV
  approximation (Google can't truck-route). `route_matrix` stays `DRIVE` + the haversine fallback.

---

## 11. API — `server/api/routes/project_contexts.py` (NEW)
*(patterns from `api/routes/projects.py`; deps from `api/deps.py`)*
- `GET  /projects/{project_uuid}/context` → `ProjectContextRead` (read conn).
- `GET  /projects/{project_uuid}/context/history` → `list[ProjectContextHistory]` (governance).
- `PUT  /projects/{project_uuid}/context` → `ProjectContextUpdate` → `save` (UoW) → `ProjectContextRead`.
- `POST /projects/{project_uuid}/context/resolve` → run §7 resolve (UoW + retrieval/llm/maps).
- Register router in `api/main.py`.

### 11.1 HITL user (governance `benutzer`)
fastapi-users is **not wired yet** (Capstone, not production), so every governance user field gets a
hardcoded placeholder: a module constant `DEFAULT_USER = "DEFAULT_USER"` (define once, reference it
everywhere `benutzer` is written). Auth is HTTP-only (don't import `auth/` in `server/`), so when
fastapi-users lands, the API layer obtains the authenticated user and **passes the user id/name down**
into `ProjectContextService.save` (replacing `DEFAULT_USER`); the calc-flow review threads the
conversation's user through `run_service` → the save call.

---

## 12. UI

### 12.1 Pre-Gate-A review (primary) — `ui/src/views/workspace/InterruptPanel.tsx`
- New `STAGE_PROJECT_CONTEXT_REVIEW = "project_context_review"` + a `ProjectContextReview` component.
- Per global: current value, **address inputs as strings** (Baustelle, Deponie) with status badges
  (reuse the `BAUSTELLE_*` badges from `lieferanten-wahl`), number inputs (strip length/width, fräsgut),
  read-only `entfernung_deponie_km`; for `konflikt` variables show chat-vs-saved with a pick.
  Actions map to **Confirm / Override / resolve Conflict**. Submit posts an update in the resume
  (`CalculationResume.projekt_kontext`).
- **Remove** the per-position Baustelle field from `MethodReview` (added on `lieferanten-wahl`); keep
  the supplier picker.

### 12.2 Project-level panel (optional) — `ui/src/views/main/ProjectContextPanel.tsx` (NEW)
Hooks in `ui/src/api/project-context.ts` (copy `ui/src/api/projects.ts`): `useProjectContext`,
`useUpdateProjectContext`, `useProjectContextHistory`. Mount in `ProjectDetails.tsx`. Edit context
outside a calc; show version history (governance).

### 12.3 Types
After the schemas land + `export_schema.py` update → `npm run gen:types`.

### 12.4 Reasoning output UX (NEW) — workspace conversation rendering
The calc reasoning streams as `text_delta` SSE events (`run_service.py`, `_format_reasoning`). Change
the renderer (the component in `ui/src/views/workspace/` / `useWorkspaceConversation` that accumulates
the calculator's reasoning) to:
- **Collapsed by default to the most recent line**, with an **expand toggle** revealing the full
  line-by-line history (keep accumulating all deltas; only the display collapses).
- A **prominent activity indicator** ("Berechnung läuft…" + spinner) bound to the streaming /
  `awaiting_input` state (`CalculationStatus.RUNNING`), since the current cue is too subtle.
- (Locate the exact component during impl; reasoning arrives as `EVENT_TEXT_DELTA` content and the
  result as `function_call_output` — see `run_service.py` constants.)

---

## 13. Refactor delta from `lieferanten-wahl`

- **`graph.py`:** delete `locate_baustelle` geocoding + per-position `baustelle_*` writes; split its
  ranking into `rank_lieferanten` (post-classify). `bind_lieferant` reads coords from `projekt_kontext`.
  `compute` injects `entfernung_deponie_km` from project context.
- **`state.py`:** per-position `baustelle_*` fields superseded by `projekt_kontext: dict` (+ reconcile
  state). Keep `BAUSTELLE_*` status constants. `lieferanten_vorschlag`/`lieferant_*` unchanged.
- **`InterruptPanel.tsx`:** remove the Baustelle field from `MethodReview`; remove `baustelle` from the
  Gate-A resume (moves to `projekt_kontext`).
- **`kontext_variablen.py`:** keep `entfernung_deponie_km` as a last-resort fallback; `fraesgut_klasse`
  keeps its per-position def (now also fed by the project default); the Baustelle `koordinate()` vars
  added there can be removed (coords are project-level, not engine variables) — verify no other refs.
- Keep the rest of `lieferanten-wahl` (the `entfernung_km` split, `formel.py` rewiring,
  `lieferant_ranking.py`, `maps/geo.py`, `lade_preise` in `store.py`).

---

## 14. Config (`server/shared/config.py`)
- `calculator_lieferant_radius_km: float = 100.0`
- `calculator_hgv_detour_factor: float = 1.0`
- (reused) `google_static_maps_api_key`, `google_maps_geocoding_url`, `google_maps_route_matrix_url`,
  `maps_request_timeout_seconds`, `calculator_mock`.

---

## 15. Tests / eval
- **Repo (integration, test DB):** `supersede` closes out the current row (`gueltig_bis`,
  `ist_aktuell=false`) and inserts `version+1`; `current()` returns the `ist_aktuell` row per variable;
  `history()`/`as_of()` ordered; a prior version's value/source are never mutated.
- **Resolver (mock):** the dedicated `resolve_globale` over retrieved snippets → value + provenance;
  location → geocode; `save` geocodes a changed address, recomputes `entfernung_deponie_km`, supersedes
  to a HITL version with `benutzer` + `quelle_referenz`.
- **Graph (mock):** chat-extracted global → reconcile `konflikt` vs saved; the review gate surfaces
  Confirm/Override/Conflict; an override saves (new version) and flows into the per-position calc
  (deponie distance reflects the routed value; ranking uses the project baustelle).
- **Ranker (mock):** radius filter; **no-carrier-in-radius → nearest + WARNING**.
- **Geometry (engine):** booked menge wins; `strip_*` fallback derives `laenge_m`/`flaeche_m2`.
- **UI:** reasoning collapses to latest + expands to history; activity indicator visible while running.

> Sandbox note: build env may lack `uv`/`pytest`/`pydantic_settings` + populated `ui/node_modules`;
> only the pure `kalkulation_v2` engine runs there. Validate with `uv run pytest` + `npm run build`.

---

## 16. Touched files (checklist)

**New:** `db/tables/project_context_values.py` · `models/project_context.py` ·
`models/project_context_schema.py` · `repositories/project_context_values.py` ·
`services/kalkulation_v2/globale_variablen.py` · `services/project_context/{__init__,service,llm}.py` ·
`scripts/seed/prompts/project_context_resolve.prompt` · `api/routes/project_contexts.py` · `ui/src/api/project-context.ts` ·
`ui/src/views/main/ProjectContextPanel.tsx` (optional) · tests under `tests/unit/**` + `tests/integration/**`.

**Modified:** `db/tables/__init__.py` · `db/unit_of_work.py` · `scripts/export_schema.py` ·
`api/main.py` · `config.py` · `services/calculator/graph.py` (topology; chat-extends-globals; load +
reconcile + review; rank split; injection; remove per-position baustelle) · `services/calculator/state.py`
(`projekt_kontext` + reconcile; drop per-position baustelle) · `services/calculator/run_service.py`
(save the review, thread `benutzer`) · `services/calculator/llm_calls.py` (chat-extract globals) ·
`services/calculator/lieferant_ranking.py` (radius + nearest fallback +
warning + HGV factor) · `services/kalkulation_v2/kontext_variablen.py` (remove baustelle coord vars) ·
`ui/src/views/workspace/InterruptPanel.tsx` (review stage; remove per-position baustelle) ·
`ui/src/api/calculations.ts` (`CalculationResume.projekt_kontext`) ·
`ui/src/views/main/ProjectDetails.tsx` (mount panel) · the workspace reasoning renderer (§12.4).

**New prompt:** `PromptType.PROJECT_CONTEXT_RESOLVE` + `scripts/seed/prompts/project_context_resolve.prompt`
(dedicated structured resolution over hybrid-RAG chunks — **not** `EKT_LANGTEXT_EXTRACT`).

**Canonical files to copy from:** `tables/lv_items.py`, `tables/messages.py` (JSONB),
`models/project.py`, `models/project_schema.py`, `repositories/lv_items.py` (versioned/upsert-ish),
`db/unit_of_work.py`, `api/deps.py`, `api/routes/projects.py`, `services/retrieval/service.py`
(`retrieve_context`), `services/calculator/llm_calls.py` (`extract_value`), `scripts/bootstrap_tables.py`,
`scripts/export_schema.py`, `ui/src/api/projects.ts`, `ui/src/views/main/ProjectDetails.tsx`,
`ui/src/views/workspace/InterruptPanel.tsx`.

---

## 17. Implementation order (phased)
1. **Versioned persistence (SCD-2)** — table + `ContextQuelle`/models + repo
   (`supersede`/`current`/`history`/`as_of`) + UoW + bootstrap; repo integration tests (supersede
   closes out + inserts; a prior version is never mutated; one `ist_aktuell` per variable).
2. **Resolver** — `globale_variablen` registry + `project_context` service (hybrid `retrieve_context`
   + the new `PROJECT_CONTEXT_RESOLVE` prompt + geocode/route), with mock fixtures; service unit tests.
3. **API + optional panel** — endpoints (incl. history) + `benutzer` threading + `export_schema` +
   `gen:types` + `ProjectContextPanel` (test resolve/save/history standalone, decoupled from the graph).
4. **Graph integration** — chat-extends-globals; `load_project_context` + reconcile +
   `project_context_review` (Confirm/Override/Conflict); `rank_lieferanten` split; per-position
   injection; `run_service` save; mock graph tests.
5. **Geometry + ranker** — strip fallback (§9); radius + nearest-fallback WARNING + HGV factor.
6. **Reasoning UX** — collapse-to-latest + expand history + activity indicator (§12.4).
7. **Cleanup** — remove per-position Baustelle remnants (§13); write `PROJECT_CONTEXT_STATUS.md`.

---

## 18. Open questions / risks / deferred
- **(a) DECIDED: SCD-2** (`gueltig_bis` + `ist_aktuell`, close-out on supersede); point-in-time supported.
- **(b) DECIDED: `benutzer = "DEFAULT_USER"`** — a hardcoded constant placeholder for now (Capstone);
  thread the real authenticated user when fastapi-users lands.
- **HGV routing** — Google can't truck-route; the detour factor is a stopgap. Revisit a truck provider
  (HERE/PTV/OSRM) if haul accuracy matters for bids.
- **Resolution trigger** — lazy on first calc (v1) vs. eager at project creation/ingestion.
- **Multi-section projects** — one context stream per project assumes one Baustelle/section; a
  multi-section project would need context keyed below project level (deferred).
- **(c) DECIDED: dedicated `PROJECT_CONTEXT_RESOLVE` prompt, ONE variable per call** — focused
  retrieval + extraction per global (no multi-variable pass; avoids context rot). Leverages hybrid
  `retrieve_context`, then extracts that one variable. **Not** `EKT_LANGTEXT_EXTRACT` (LV-Langtext domain).
- **Stichtag / price coverage** — unchanged from `lieferanten-wahl`.
