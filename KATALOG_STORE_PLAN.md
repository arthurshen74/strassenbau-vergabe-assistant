# Katalog Store Plan

Persist the entire `kalkulation_v2` catalog (Leistungen, Bauverfahren, Vorgänge,
Ausführungsarten, Betriebsarten, Formeln, Variablen, Stammdaten, Baustoffe,
Lieferanten + Preise, Maschinen, Leistung→Bauverfahren-Mapping, Globale Variablen)
to Postgres, with a draft/active lifecycle and bundle-transactional writes, without
the calculation engine or the calculator StateGraph noticing that the catalog moved.

This is **Part A + Part B of the Recipe Compiler effort**. The compiler intelligence
(NL Construction German → recipe bundle) is **Part C and explicitly out of scope
here** — this plan only lays the store and a dumb end-to-end chat harness for it.

Companion docs: `DATA_ARCHITECTURE.md`, `server/shared/services/kalkulation_v2/ARCHITECTURE.md`,
`CALCULATOR_GATE_FLOW_PLAN.md`.

---

## 1. Locked decisions

1. **DB is the single source of truth at runtime.** The `kalkulation_v2` data
   modules (`leistungen.py`, `bauverfahren.py`, …) are demoted to *seed fixtures*
   (and unit-test fixtures). They are NOT deleted. The API process overwrites the
   module-level dicts from Postgres at startup; a process that never calls the
   provider (unit tests, `store.py __main__`) keeps running on the fixture data
   unchanged.
2. **Lifecycle, not mutation.** Every catalog row has `status`
   (`entwurf | aktiv | archiviert`) and `version`. Editing never mutates: a change
   inserts the next version as `entwurf`; activation archives the current `aktiv`
   row and promotes the draft. Exactly one `aktiv` row per natural key (partial
   unique index — same pattern as `project_context_values`). Reproducibility of
   past calculations is already carried by `calculation_ground_truth.gold_variables`
   (resolved values are stored); catalog versioning is for audit and drafts, not
   for replay.
3. **String codes are the only domain identity.** `code` (or `name` for
   Formeln/Variablen) is the natural key threaded through formulas, mappings,
   ground truth, and eval. The Pydantic `id: UUID` fields
   (`default_factory=uuid4`, regenerated on every import) are unused except as a
   pointless indirection in the price lookup — they are **deleted** in the
   Step-0 prefactor (§11): `BaustoffPreis.baustoff_id` becomes `baustoff_code`,
   `preis_fuer` takes a code. Row UUIDs exist only at the storage layer (PKs,
   version-pinned junction FKs, `KatalogZeile` envelope) and never appear in
   domain models.
4. **The engine keeps eating dicts.** A provider loads Postgres into the *existing*
   module-level dicts **in place** (`d.clear(); d.update(...)`). `Kalkulator`,
   `graph.py`, `binden.py`, `worklist.py` are not rewritten. Derived state is
   rebuilt explicitly (§5).
5. **The write unit is a bundle.** The service accepts a `KatalogBundle` (any subset
   of catalog entities that belong together), validates it as a whole, and persists
   it in one Unit-of-Work transaction as drafts sharing a `bundle_uuid`. Activation
   is likewise per bundle, atomic.

---

## 2. Non-goals (do not build)

- No compiler intelligence, no prompt engineering beyond the placeholder in §8.
- No admin/CRUD UI. The only UI work is the one interrupt stage in §9.
- No org/tenant scoping of the catalog. One global catalog.
- No migration framework. New tables register in `server/shared/db/tables/__init__.py`
  and are created by `server/scripts/bootstrap_tables.py`, like every other table.
- No worker-process reload plumbing (the worker does not consume the catalog today).
- No deletion or restructuring of the `kalkulation_v2` fixture modules.
- `positionen.py` (50 demo/eval positions) and `eval/` fixtures are untouched —
  they are instance data, not catalog.
- No backwards-compat shims. `build_store()` keeps its shape.

---

## 3. Tables

All tables live in the domain MetaData (`shared/db/metadata.py`), one file per table
under `server/shared/db/tables/`, names prefixed `katalog_`. German domain column
names, `*_uuid` PK with `gen_random_uuid()`, house naming conventions.

### 3.1 Shared lifecycle columns

New helper `server/shared/db/tables/katalog_lifecycle.py`:

```python
def lifecycle_spalten() -> list[Column]:
    # fresh Column objects per call (SQLAlchemy columns are single-use)
    return [
        Column("version", Integer, nullable=False),           # 1,2,3… per natural key
        Column("status", Text, nullable=False),               # KatalogStatus value
        Column("bundle_uuid", UUID(as_uuid=True), nullable=True),  # rows written together
        Column("benutzer", Text, nullable=True),               # author ("seed" for fixtures)
        Column("gueltig_ab", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("gueltig_bis", DateTime(timezone=True), nullable=True),  # set on archive
        Column("erstellt_am", DateTime(timezone=True), nullable=False, server_default=func.now()),
    ]
```

Each lifecycle table additionally declares, with its own natural-key column
(`code` or `name`):

- `UniqueConstraint(<key>, "version")`
- `Index("uq_<table>_aktiv", <key>, unique=True, postgresql_where=text("status = 'aktiv'"))`

`KatalogStatus` is a `StrEnum` in `server/shared/models/katalog.py`
(`ENTWURF = "entwurf"`, `AKTIV = "aktiv"`, `ARCHIVIERT = "archiviert"`) — the single
source for these values; never re-type them.

### 3.2 Lifecycle tables (natural key → payload columns)

| Table | Key | Payload columns (beyond lifecycle) |
|---|---|---|
| `katalog_leistungen` | `code` | `name` Text, `beschreibung` Text NULL, `standard_kennung` Text NULL, `einheit` Text NULL |
| `katalog_bauverfahren` | `code` | `name` Text |
| `katalog_vorgaenge` | `code` | `name` Text, `ausfuehrungsart_code` Text NULL, `betriebsart_code` Text NULL, `leistung_variable` Text NULL, `kosten_bindung` JSONB, `kostenvariablen` JSONB |
| `katalog_ausfuehrungsarten` | `code` | `name` Text, `geraetebezug` Text NULL |
| `katalog_betriebskategorien` | `code` | `bezeichnung` Text, `beschreibung` Text NULL |
| `katalog_betriebsarten` | `code` | `bezeichnung` Text, `kategorie_code` Text, `einheit` Text NULL, `beschreibung` Text NULL |
| `katalog_formeln` | `name` | `ergebnis_variable` Text, `ausdruck` Text, `einheit` Text NULL |
| `katalog_variablen` | `name` | `gruppe` Text (`stammdaten \| kontext \| formel`), `bezeichnung` Text, `beschreibung` Text NULL, `einheit` Text NULL, `datentyp` Text, `llm_kontext` Text NULL, `aufloesung` JSONB |
| `katalog_globale_variablen` | `name` | `bezeichnung` Text, `einheit` Text NULL, `datentyp` Text, `ist_standort` Boolean, `erforderlich` Boolean, `ziel_variable` Text NULL, `rag_prompt` Text |
| `katalog_baustoffe` | `code` | `name` Text, `rohdichte_t_pro_m3` Numeric, `verdichtungsfaktor` Numeric, `kategorie` Text NULL, `koernung` Text NULL, `einheit` Text, `basispreis_eur_pro_t` Numeric NULL, `basispreis_eur` Numeric NULL |
| `katalog_lieferanten` | `code` | `name` Text, `standort` Text NULL, `breitengrad` Numeric NULL, `laengengrad` Numeric NULL |
| `katalog_maschinen` | `code` | `hersteller` Text, `modell` Text, `ausfuehrungsart_code` Text, `eigenschaften` JSONB, `leistungsprofile` JSONB |
| `katalog_leistung_bauverfahren` | `leistung_code` | `bauverfahren_codes` JSONB (ordered array; first entry = default) |

JSONB payloads are exactly the `model_dump(mode="json")` of the corresponding
Pydantic structures (`AufloesungsSchritt` list, `Kostenart -> str` map,
`MaschinenWert` bag, `Leistungsprofil` list); Pydantic validates on load. Do not
normalize these into child tables.

The `katalog_variablen.gruppe` discriminator preserves the three fixture sources
(`STAMMDATEN_VARIABLEN`, `KONTEXT_VARIABLEN`, `FORMEL_VARIABLEN`) so the provider
can rebuild the three dicts and their merge (`KATALOG`) exactly. Seed writes what
the modules export — `FORMEL_VARIABLEN` rows are stored, not derived.

### 3.3 Non-lifecycle tables (immutable rows / children of a versioned parent)

| Table | Columns |
|---|---|
| `katalog_bauverfahren_vorgaenge` | `bauverfahren_uuid` FK → `katalog_bauverfahren` ON DELETE CASCADE, `reihenfolge` Integer, `vorgang_code` Text; UNIQUE(`bauverfahren_uuid`, `reihenfolge`) |
| `katalog_lieferanten_preise` | `lieferant_code` Text, `baustoff_code` Text, `preis_eur_pro_t` Numeric, `gueltig_ab` Date, `gueltig_bis` Date NULL, `erstellt_am` timestamptz |

Junction rows belong to a *specific version row* of a Bauverfahren (by UUID) and are
rewritten when a Bauverfahren is superseded. Prices reference codes (version-
independent): superseding a Lieferant must not orphan its price history. Price
validity (`gueltig_ab/bis`) is *domain* time — a price correction inserts a new row,
never updates.

Cross-entity code references (`vorgang_code`, `ausfuehrungsart_code`,
`kategorie_code`, `baustoff_code`, …) get **no DB-level FK** — codes are not unique
across versions. Referential integrity is enforced by the bundle validator (§7),
consistent with validate-at-the-boundary.

---

## 4. Models and repository

- `server/shared/models/katalog.py`: `KatalogStatus` (StrEnum), `KatalogZeile`
  (envelope: uuid, key, version, status, bundle_uuid, benutzer, gueltig_ab/bis,
  payload dict) for the CRUD surface, and `KatalogBundle` (§7). Payload contracts
  remain the existing `kalkulation_v2.model` classes — no parallel DTOs.
- `server/shared/repositories/katalog.py`: **one generic repository**, parameterized
  by an entity registry (table, key column, payload column set). Thirteen
  near-identical repositories is exactly the >3-instances case; do not write one
  file per table. Surface:
  - `aktive(entitaet) -> list[KatalogZeile]`
  - `entwuerfe(entitaet) -> list[KatalogZeile]` / `nach_bundle(bundle_uuid)`
  - `neue_version(entitaet, key, payload, benutzer, bundle_uuid) -> KatalogZeile`
    (next version per key, `status=entwurf`)
  - `aktiviere(zeile_uuid)` — archives the current `aktiv` row of the same key
    (sets `gueltig_bis`, mirrors the SCD-2 supersede in
    `repositories/project_context_values.py` incl. the `clock_timestamp()` note),
    then flips the draft to `aktiv`
  - `archiviere(zeile_uuid)` — discard a draft or retire an active row
  - junction/price accessors for the two non-lifecycle tables
- Register on the UoW as `uow.katalog`.

---

## 5. KatalogProvider

New `server/shared/services/kalkulation_v2/provider.py`.

```python
async def lade_katalog(conn: AsyncConnection) -> None:
    """Load all aktiv rows, validate into domain models, refill the module dicts
    in place, rebuild derived state. Idempotent; call at startup and after writes."""
```

Load order (respects embedding dependencies):

1. `katalog_betriebskategorien`, `katalog_betriebsarten` → the dicts in `betriebsarten.py`
2. `katalog_ausfuehrungsarten` → `AUSFUEHRUNGSARTEN`
3. `katalog_formeln` → `FORMELN`; `katalog_variablen` by `gruppe` →
   `STAMMDATEN_VARIABLEN`, `KONTEXT_VARIABLEN`, `FORMEL_VARIABLEN`
4. `katalog_baustoffe` → `BAUSTOFFE`
5. `katalog_lieferanten` + `katalog_lieferanten_preise` → `LIEFERANTEN`, price
   rows validating directly into `BaustoffPreis` (field-for-field after the
   Step-0 prefactor; replaces the fixture-time `lade_preise` call for the DB path)
6. `katalog_maschinen` → `MASCHINEN` (and any per-Ausführungsart index `maschinen.py` keeps)
7. `katalog_vorgaenge` → `VORGAENGE`, embedding the loaded `Ausführungsart`
   instance by `ausfuehrungsart_code`
8. `katalog_bauverfahren` + junction → `BAUVERFAHREN`, embedding loaded `Vorgang`
   instances ordered by `reihenfolge`
9. `katalog_leistungen` → `LEISTUNGEN`; `katalog_leistung_bauverfahren` →
   `LEISTUNG_BAUVERFAHREN`
10. `katalog_globale_variablen` → `GLOBALE_VARIABLEN`

All refills are **in place** (`clear()` + `update()`) so every existing importer
(`graph.py`, `binden.py`, `lieferant_ranking.py`, `worklist.py`,
`project_context/*`) sees the new data through its existing reference.

Derived state to rebuild (in this order, after the dicts):

- `store.KATALOG` — refill in place from the three variable dicts.
- `baustoff_suche` — add `def baue_index() -> None` that reassigns the module
  `_INDEX = _BM25(BAUSTOFFE)`; module import keeps building the fixture index so
  non-DB processes are unaffected. Provider calls `baue_index()`.
- `globale_variablen.GLOBAL_VAR_NAMES` / `ERFORDERLICHE_GLOBALE` — currently
  `frozenset`s, which cannot be refilled in place and are imported by value
  elsewhere. Change both to plain `set`s refreshed via `clear()`/`update()`
  (grep all importers; no other change to their use sites).

Check for any other module-level derivation over the catalog dicts
(`grep -n "BAUSTOFFE\|LEISTUNGEN\|BAUVERFAHREN\|VORGAENGE\|MASCHINEN" server/shared --include=*.py -r`)
and rebuild it here; anything computed at import time from catalog data is suspect.

Wiring:

- FastAPI lifespan (API startup): `async with engine.connect(): await lade_katalog(...)`.
  If the katalog tables are empty, log one warning and keep the fixture data —
  a dev DB without seed must not crash the API.
- After a successful bundle activation (§7), the service calls `lade_katalog`
  again on a fresh connection. Single-process deployment is assumed and documented;
  an in-flight position calculation may observe a catalog swap between gates
  (identical to today's redeploy semantics — acceptable, out of scope).

---

## 6. Seed

`server/scripts/seed/seed_katalog.py` (runnable via `uv run python -m ...`, same
style as the existing seed scripts):

- Reads the fixture modules and writes every entity as `version=1`,
  `status=aktiv`, `benutzer="seed"`, `bundle_uuid=NULL`. Junction and price rows
  written from `Bauverfahren.vorgaenge` order and `lieferanten_preise.lade_preise`
  data respectively.
- Idempotent: if any `katalog_*` table already has rows, abort with a message.
  `--reset` truncates all `katalog_*` tables first and reseeds.

---

## 7. Bundle service and API

`server/shared/services/katalog/service.py` + `validierung.py`.

```python
class KatalogBundle(BaseModel):
    """One coherent catalog change set: any subset of entities that belong together."""
    leistungen: list[Leistung] = []
    bauverfahren: list[Bauverfahren] = []          # vorgaenge referenced by code in transport,
    vorgaenge: list[Vorgang] = []                   # embedded on load like the fixtures
    ausfuehrungsarten: list[Ausführungsart] = []
    betriebsarten / betriebskategorien: ...
    formeln: list[Formel] = []
    variablen: list[VariableDefinition] = []        # incl. gruppe assignment
    baustoffe: list[Baustoff] = []
    leistung_bauverfahren: dict[str, list[str]] = {}
```

(Exact transport shape for Bauverfahren→Vorgang references — embedded vs. code
list — is the implementer's choice; codes are simpler and match the junction.)

Validation (`pruefe_bundle(bundle, katalog_stand) -> list[str]`, pure, no I/O;
`katalog_stand` = the union of active catalog keys and the bundle's own keys):

1. Every `Formel.validieren()` passes against the known-variable union.
2. The formula dependency graph (existing ∪ bundle) is acyclic — static check,
   don't wait for the runtime cycle detector.
3. Every `Vorgang.kostenvariablen` value is producible: names a variable whose
   definition (existing or in-bundle) carries a `FORMEL`, `KONSTANTE`, or
   `STAMMDATEN` step, or is a `kontext`-gruppe variable.
4. Every code reference resolves: `Vorgang.ausfuehrungsart_code`,
   `Vorgang.betriebsart_code`, `Betriebsart.kategorie_code`, junction
   `vorgang_code`s, mapping `leistung_code`/`bauverfahren_codes`.
5. New keys don't collide with active keys of a *different* entity type sharing
   the variable namespace (`katalog_variablen` names, `formeln` names, and
   `globale_variablen` names must stay overlap-free — the `KATALOG` merge in
   `store.py` assumes it).
6. A bundle key equal to an existing active key means *supersede* (allowed);
   flag it in the validation report as an update, not an error.

Service operations (each one UoW):

- `entwurf_speichern(bundle, benutzer) -> bundle_uuid` — validate, insert all rows
  as `entwurf` sharing one `bundle_uuid`.
- `bundle_aktivieren(bundle_uuid)` — re-validate against the *current* active
  catalog, then activate every row of the bundle atomically; reload the provider.
- `bundle_verwerfen(bundle_uuid)` — archive the drafts.

API (`server/api/routes/katalog.py`, thin wrappers only):

- `GET /katalog/{entitaet}` — active rows (envelope form)
- `GET /katalog/entwuerfe` — drafts grouped by bundle
- `POST /katalog/bundle/pruefen` — validation report, no write
- `POST /katalog/bundle` — draft save
- `POST /katalog/bundle/{bundle_uuid}/aktivieren` / `.../verwerfen`
- `POST /katalog/neu-laden` — re-read the persisted catalog into the running engine (for edits
  that bypassed a bundle activation; activation itself reloads automatically)

Run `npm run gen:types` after the routes exist.

---

## 8. Chat harness (Part B — deliberately dumb)

New `server/shared/services/rezept_autor/` (graph.py, prompts.py, run_service.py),
following the calculator service's wiring pattern (`services/calculator/run_service.py`)
for conversation + SSE + checkpointer. New conversation topic for recipe authoring.

Graph, minimal:

1. `entwerfen` — one LLM call, structured output = `KatalogBundle` (JSON schema from
   the Pydantic model). Placeholder system prompt: the active catalog's Leistungen/
   Vorgänge/Variablen index as context, instruction to reuse existing Vorgänge and
   variables where possible and to write `Formel.ausdruck` in the DSL. No further
   sophistication — the real prompt design is Part C.
2. `pruefen` — run `pruefe_bundle`; on errors, loop back to `entwerfen` with the
   error list appended (max 3 attempts, then surface errors to the human).
3. `rezept_review` — **interrupt** carrying the bundle + validation report +
   supersede flags. Resume payload: `{bestaetigt: bool, feedback: str | None,
   aktivieren: bool}`. Feedback loops back to `entwerfen`; `bestaetigt` persists
   via `entwurf_speichern`, and `aktivieren=true` additionally activates + reloads.

Testing: integration test with a mocked LLM returning a fixed valid bundle —
describe → review → confirm+activate → the new Leistung is calculable through
`kalkuliere_kontext` in the same test.

---

## 9. UI (minimal, hand-written)

One new stage in `ui/src/views/workspace/InterruptPanel.tsx`:
`STAGE_REZEPT_REVIEW = 'rezept_review'`, plus a `RezeptReview` component — a plain
sectioned rendering of the bundle (Leistung; Vorgänge with Kostenarten; Formeln as
`name = ausdruck [einheit]` rows; Variablen; mapping), the validation report, the
supersede flags, and Bestätigen / Feedback / Verwerfen controls with an
"aktivieren" checkbox. No generic form framework, no catalog pickers — this UI
gets redesigned in Part C; keep it under ~200 lines.

Entry point: reuse the existing conversation UI with the new topic (however the
calculator conversation is launched today; no new routing surface).

---

## 10. Acceptance criteria (all must hold)

1. `uv run pytest` — entire suite green.
2. **Parity harness** `server/scripts/check_katalog_parity.py`:
   seeded DB → `lade_katalog` → deep-compare every refilled dict against a fresh
   import of the fixture modules (`model_dump()` comparison, *excluding* the
   ephemeral `id` UUID fields) → then run `kalkuliere(pos)` for all 50
   `POSITIONEN` on both catalog states and assert byte-identical EKT/EP results.
   Ships as a script AND as an integration test.
3. `server/scripts/eval_calculator` grading output unchanged against the DB-backed
   catalog.
4. Unit tests for every validator rule in §7 (one failing fixture each).
5. Integration test: bundle draft → activate → provider reload → new recipe
   calculable (may be the same test as §8's).
6. Harness happy path works end-to-end with the mocked LLM.
7. `npm run build` green; generated types regenerated, not hand-edited.

## 11. Execution order

0. **Prefactor (own commit):** delete the unused `id: UUID` fields from all
   `kalkulation_v2.model` domain classes (`Leistung`, `Bauverfahren`, `Vorgang`,
   `Ausführungsart`, `Maschine`, `Baustoff`, `Baustofflieferant`); change
   `BaustoffPreis.baustoff_id: UUID` → `baustoff_code: str` and
   `Baustofflieferant.preis_fuer(baustoff_code: str, stichtag)`. Call sites:
   `lieferanten_preise.py:665,674`, `lieferanten.py:127`, `materialien.py:118-134`,
   `calculator/lieferant_ranking.py:83`. Full test suite green before step 1.
1. Tables + models + generic repository + bootstrap registration (§3, §4)
2. Seed script (§6) → parity harness first version (dict comparison only)
3. Provider + derived-state rebuilds (§5) → full parity harness green (criteria 2–3)
4. Bundle service + validation + API (§7) (criteria 4–5)
5. Chat harness + interrupt stage + UI (§8, §9) (criteria 6–7)

Work on a feature branch (`katalog-store`). Steps 1–3 must be green before 4–5
start; do not begin §8 until the parity harness passes.
