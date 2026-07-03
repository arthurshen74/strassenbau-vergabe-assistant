# Katalog Agent Plan

A conversational interface over the persisted catalog (the Katalog Store, see
`KATALOG_STORE_PLAN.md`), built in three phases:

- **Phase 1 — Reads.** A chat agent with a complete read-tool surface over every catalog
  entity and every relationship, forward and reverse ("Welche Lieferanten können AC 22 T S
  liefern?"). No mutations.
- **Phase 2 — Mutations.** The same agent gains write tools. Every write is a single-entity
  (or minimal) `RezeptBundle` draft → HITL confirm → activate → provider reload, plus a global
  catalog version (`katalog_stand`).
- **Phase 3 — Recipe compiler.** NL Construction German → full multi-entity bundle. Reuses
  the Phase-1 tool surface for discovery and the Phase-2 write path for persistence. Sketched
  here only; own plan when Phases 1–2 stand.

**Phase 1's tool list (§3) is the review artifact: it is meant to be cross-checked against
the relationship matrix (§4) before any implementation starts.**

---

## 1. Decisions

1. **Tools, not context stuffing; tools, not MCP.** The catalog will outgrow any prompt
   (today's data covers a handful of small Mill-and-Fill projects). Discovery is therefore
   tool-based from the start. The tools are plain in-process function calling inside the
   agent's LangGraph loop — no MCP; MCP is a possible future *product surface* for external
   clients, never internal plumbing.
2. **Tools read the DATABASE, not the engine's module dicts.** The DB is the source of truth,
   carries drafts and history, and works from any process. Default visibility is `aktiv` rows;
   drafts and archived versions are reachable only through explicit parameters/tools. The
   engine's in-memory dicts remain a calculation-time concern and are untouched by this plan.
3. **One read layer.** All tool logic lives in `server/shared/services/katalog/lese_modell.py`
   (on `KatalogRepository` / SQL; where-used analysis parses stored formula expressions via
   `Formel.eingaben()`). Tool handlers are thin; the agent graph contains no queries.
4. **German tool names with a fixed verb grammar** (§2). The LLM discovers capability through
   consistent naming, the reviewer through the numbered list.
5. **Formulas are data; the DSL vocabulary is code.** Read tools expose the vocabulary
   (`zeige_dsl_funktionen`) so the agent can answer "what can formulas do" and, later, author
   within it. Extending `_FUNKTIONEN` stays an engineering change (stated invariant).
6. **Machine "categories" are two explicit facets with decided vocabulary:** Facet A is the
   **Geräteklasse** — the display/agent term for the Ausführungsart slot a machine fills
   (`Maschine.ausfuehrungsart_code`; exactly ONE per machine; answers "which machines are
   interchangeable for this job step"). Facet B is its **Betriebsarten** — the operation
   modes it masters, one Leistungsprofil (productivity) each, grouped by Betriebskategorie
   (MANY per machine; answers "what can it do, how fast"). Sprachregelung: the agent speaks
   „Geräteklasse" and „Betriebsart"; entity names, tables, codes and tool parameters keep
   the technical terms (`ausfuehrungsart_code` etc.) — codes are the contract, the words are
   UI. Calculation-time precedence (binden.py): machine Leistungsprofil → catalog default
   (Stammdaten/Formel) → HITL.

## 2. Tool conventions

- `liste_…` — enumerate a collection; compact rows; optional filters; `limit` (default 50,
  hard cap 200) + `treffer_gesamt` in the envelope so truncation is never silent.
- `zeige_…` — one entity by natural key, fully resolved one reference-level deep, including
  its reverse edges ("used by …").
- `finde_…` — a targeted relationship query (the "foreign key reads").
- `suche_katalog` — ranked text search across entities (the generalized `baustoff_suche`
  BM25 pattern; substring fallback acceptable in v1).
- `erklaere_…` / `verwendung_…` — transitive analysis (derivation trees, where-used /
  impact).
- Common parameters: `status` (default `aktiv`; `entwurf`/`archiviert` explicit),
  `stichtag` (date, default today) wherever prices/validity are involved.
- Every tool returns JSON-compact envelopes designed for LLM consumption (short keys, no
  nulls spam); the chat UI renders tool calls/results with the existing function-call
  message components.
- All Phase-1 tools are read-only by construction (no write reachable from the read layer).

## 3. Phase 1 — the complete read-tool list

### Meta and search

- **T1 `katalog_uebersicht()`**
  Counts per entity, global catalog version + last change (timestamp, benutzer; see §6 —
  until `katalog_stand` exists, derived as `max(erstellt_am/gueltig_ab)` across tables),
  open-draft count.
  *Beantwortet: „Was ist alles im Katalog? Wann wurde er zuletzt geändert und von wem?"*

- **T2 `suche_katalog(text, entitaeten?, limit?)`**
  Ranked text search across all entities (code, name, Bezeichnung, Beschreibung).
  Returns (entitaet, schluessel, name, score).
  **Spec: lexical, not semantic.** BM25 (the `baustoff_suche._BM25` class generalized) with
  substring fallback; no embeddings in v1. Rationale: controlled technical vocabulary (codes,
  DIN designations, Körnungen) matches lexically and can only return real catalog keys — and
  the caller is an LLM that reformulates on a miss, so the tool need not be semantic.
  Upgrade path if eval shows synonym misses: the existing ES + embedding pipeline.
  *Beantwortet: „Gibt es irgendwas zu ‚Bankett'?"*

- **T3 `zeige_dsl_funktionen()`**
  Static: the formula language — operators, comparisons, ternary, and the `_FUNKTIONEN`
  whitelist with one-line semantics and an example each.
  *Beantwortet: „Welche Funktionen darf eine Formel benutzen?"*

### Leistungen

- **T4 `liste_leistungen(filter_text?, einheit?)`**
  Compact: code, name, einheit, #Bauverfahren-Kandidaten.
- **T5 `zeige_leistung(code)`**
  Full detail + ordered Bauverfahren candidates (first = default) + `standard_kennung`.
  *Beantwortet: „Welche Bauverfahren gibt es für die FSS, und welches ist Standard?"*

### Bauverfahren

- **T6 `liste_bauverfahren(filter_text?)`**
  Compact: code, name, #Vorgänge, #Leistungen die es nutzen.
- **T7 `zeige_bauverfahren(code)`**
  Ordered Vorgang chain (each: code, name, Ausführungsart, Kostenarten) + reverse: the
  Leistungen mapping to it.
- **T8 `finde_bauverfahren_mit_vorgang(vorgang_code)`**
  Reverse chain edge: every Bauverfahren containing the Vorgang (with position in chain).
  *Beantwortet: „Wo wird V_FSS_PROFIL überall eingesetzt?"*

### Vorgänge

- **T9 `liste_vorgaenge(ausfuehrungsart_code?, betriebsart_code?, filter_text?)`**
  Both machine facets as explicit filters (reverse edges of T12/T15 as parameters).
- **T10 `zeige_vorgang(code)`**
  Ausführungsart, Betriebsart, `leistung_variable`, `kosten_bindung`
  (cost variable ← machine property key), `kostenvariablen` per Kostenart (each variable
  with Bezeichnung + Einheit) + reverse: containing Bauverfahren.

### Ausführungsarten (Geräteklassen) / Betriebsarten / Betriebskategorien

- **T11 `liste_ausfuehrungsarten(filter_text?)`**
  Compact: code, name, geraetebezug, #Maschinen, #Vorgänge.
- **T12 `zeige_ausfuehrungsart(code)`**
  Detail + reverse both ways: machines filling this slot, Vorgänge requiring it.
  *Beantwortet: „Welche Maschinen habe ich für die Kaltfräse, und wofür wird sie gebraucht?"*
- **T13 `liste_betriebskategorien()`**
  With #Betriebsarten each.
- **T14 `liste_betriebsarten(kategorie_code?)`**
- **T15 `zeige_betriebsart(code)`**
  Detail + reverse: machines carrying a Leistungsprofil for it, Vorgänge selecting it.

### Maschinen

- **T16 `liste_maschinen(ausfuehrungsart_code?, betriebsart_code?, filter_text?)`**
  The two facets explicit (§1.6).
  *Beantwortet: „Zeig mir alle Maschinen der Geräteklasse Kaltfräse" / „… die feinfräsen
  können."*
- **T17 `zeige_maschine(code)`**
  Hersteller/Modell, slot (Ausführungsart), full property bag (each: value, unit, beleg),
  Leistungsprofile per Betriebsart (productivity + unit + profile overrides).

### Baustoffe

- **T18 `liste_baustoffe(kategorie?, koernung?, filter_text?)`**
- **T19 `liste_baustoff_kategorien()`**
  Distinct `kategorie` values with counts (the field is a loose vocabulary today — this tool
  makes that visible instead of hiding it).
- **T20 `zeige_baustoff(code)`**
  Properties (Rohdichte, Verdichtungsfaktor, Körnung, Einheit), base price(s), #Lieferanten
  carrying it, Stammdaten-Variablen bridging to it (`stammdaten_pfad` reverse edge).
- **T21 `finde_lieferanten_fuer_baustoff(baustoff_code, stichtag?)`**
  Every Lieferant with a valid ex-works price at `stichtag`, sorted by price; location
  included. Explicitly ex-works — delivered-cost ranking (routing) is a calculation-time
  concern and stays out of the catalog agent.
  *Beantwortet: „Welche Lieferanten können AC 22 T S liefern, und zu welchem Werkspreis?"*

### Lieferanten & Preise

- **T22 `liste_lieferanten(filter_text?, ort?)`**
  Compact: code, name, Standort, #Baustoffe im Sortiment.
- **T23 `zeige_lieferant(code)`**
  Location/coords + assortment summary grouped by Baustoff-Kategorie.
- **T24 `zeige_preise(lieferant_code?, baustoff_code?, stichtag?, mit_historie?)`**
  Raw price rows with validity ranges; either or both filters; `mit_historie` includes
  expired rows.
  *Beantwortet: „Was kostet FSS 0/32 bei LIEF_002, und was hat es letztes Jahr gekostet?"*

### Formeln & Variablen

- **T25 `liste_formeln(filter_text?, referenziert_variable?)`**
  `referenziert_variable` = reverse dependency filter (via `Formel.eingaben()`).
  *Beantwortet: „Welche Formeln hängen am Dieselpreis?"*
- **T26 `zeige_formel(name)`**
  `ausdruck` raw **+ LaTeX rendering + symbol legend** (deterministic AST→LaTeX walker,
  short symbols with a legend resolving each to Bezeichnung + Einheit), inputs (each with
  gruppe/Bezeichnung/Einheit), reverse: Vorgänge binding its output, Formeln referencing it.
- **T27 `liste_variablen(gruppe?, filter_text?)`**
  gruppe ∈ stammdaten | kontext | formel.
- **T28 `zeige_variable(name)`**
  Definition, Einheit, Datentyp, resolution cascade (each step: method, prompt/threshold/
  pfad/konstante), current KONSTANTE value where applicable.
- **T29 `erklaere_variable(name)`**
  The transitive derivation tree: producing formula → its inputs → their producers, down to
  KONSTANTE / STAMMDATEN / kontext leaves. The "how would this number come to be" tool.
  *Beantwortet: „Wie berechnet sich mk_fraese?"*
- **T30 `verwendung_von_variable(name)`**
  Full where-used: Formeln referencing it, Vorgänge using it as Kostenvariable or
  `leistung_variable`, `kosten_bindung` targets, Globale mit `ziel_variable` darauf.
  The impact-analysis primitive ("Was hängt alles daran, bevor ich es ändere?").

### Globale Variablen

- **T31 `liste_globale_variablen()`**
  The project-scoped set: name, Bezeichnung, erforderlich, ist_standort, `ziel_variable`,
  RAG prompt.

### Lifecycle & Audit

- **T32 `zeige_historie(entitaet, schluessel)`**
  All versions of one entry: version, status, benutzer, gueltig_ab/bis — the SCD-2 timeline.
  *Beantwortet: „Wer hat den Dieselpreis wann geändert?"*
- **T33 `liste_entwuerfe()`**
  Open draft bundles grouped by bundle, entity, and author.

## 4. Relationship matrix (the cross-check)

Every edge in the domain model, and the tool(s) covering each direction. A missing cell
would be a gap in the tool list — this table is what §3 is verified against.

| # | Edge | Forward | Reverse |
|---|---|---|---|
| E1 | Leistung → Bauverfahren (mapping, ordered) | T5 | T7 |
| E2 | Bauverfahren → Vorgang (ordered chain) | T7 | T8, T10 |
| E3 | Vorgang → Ausführungsart (slot) | T10 | T12, T9(param) |
| E4 | Vorgang → Betriebsart (profile selection) | T10 | T15, T9(param) |
| E5 | Betriebsart → Betriebskategorie | T15 | T14(param), T13(counts) |
| E6 | Vorgang → Kostenvariablen (Kostenart → name) | T10 | T30 |
| E7 | Vorgang → leistung_variable / kosten_bindung | T10 | T30 |
| E8 | Formel → Eingabe-Variablen (AST) | T26 | T25(param), T30 |
| E9 | Variable (FORMEL) ← produzierende Formel | T28, T29 | T26 |
| E10 | Variable (STAMMDATEN) → Baustoff-Eigenschaft (`stammdaten_pfad`) | T28 | T20 |
| E11 | Maschine → Ausführungsart (slot) | T17 | T12, T16(param) |
| E12 | Maschine → Betriebsart (Leistungsprofile) | T17 | T15, T16(param) |
| E13 | Lieferant → Preis → Baustoff (dated) | T23, T24 | T21, T24(param) |
| E14 | Globale Variable → ziel_variable (engine) | T31 | T30 |
| E15 | Baustoff → Kategorie (loose vocab) | T20 | T18(param), T19 |
| E16 | Jede Entität → Versionshistorie | T32 | — (T1 aggregiert) |

Soft edge (by convention, not FK): `kosten_bindung` values name machine property-bag keys
(E7↔T17's bag). T10 and T17 both display the raw keys; consistency is a Phase-2 validation
concern, not a read gap.

## 5. Architecture (Phase 1)

- **Conversation type:** new `PromptType.KATALOG_CHAT`, registered in
  `CONVERSATION_DISCRIMINATORS`; wired into `run_turn` like `rezept_autor`.
- **Agent loop: `langchain.agents.create_agent`, exactly as `project_chat_agent.py` already
  does it** — `ChatOpenAI` against OpenRouter, `@tool`-decorated handlers, usage/execution
  telemetry bridged into the existing sinks via `TelemetryCallbackHandler`, `astream_events`
  relayed to the SSE protocol. No hand-rolled loop, and nothing throwaway: Phase 2 adds
  write tools to the SAME agent (draft-first confirm, §6 — no graph interrupts needed) and
  Phase 3 reuses the loop with a bigger goal. The calculator's interrupt graph remains the
  pattern for mid-graph HITL only.
- **Tools:** one module defining the tool schemas (German names §3) and thin handlers
  delegating to `lese_modell.py`. Tool-call and tool-result messages persist as
  `FUNCTION_CALL` / `FUNCTION_CALL_OUTPUT` (existing kinds, existing UI rendering).
- **System prompt:** the Katalog-Handbuch (ontology in author's terms: Leistung = what,
  Bauverfahren = ordered how, Vorgang binds Kostenarten to variables, producibility rule),
  the tool grammar of §2, and the instruction to answer in German with compact tables.
- **DSL→LaTeX renderer:** small AST walker over the whitelisted node types +
  symbol-legend builder, in `kalkulation_v2/formel_darstellung.py`; used by T26; KaTeX
  rendering in the chat UI (markdown message path).
- **UI:** none beyond a way to start a Katalog-Chat conversation (same pattern as the
  rezept_autor entry point). No catalog browser UI — chat-first by design.

## 6. Phase 2 — Mutations (sketch — SUPERSEDED by `KATALOG_AGENT_PHASE2_PLAN.md`, the binding spec)

- **`katalog_stand`** single-row table: `version` (monotonic int), `aktualisiert_am`,
  `benutzer`. Bumped in the SAME transaction as every catalog mutation (draft save,
  activate, discard). Uses: audit display (T1), calculation provenance (stamp EKT results /
  ground truth with the catalog version — reproducibility story), cheap change detection
  for `neu-laden`.
- **Write tools** (each returns a draft for the HITL confirm gate; nothing activates
  without human confirmation): `neuer_baustoff`, `neue_maschine`, `aendere_maschine`
  (incl. slot/facet moves = superseding version with changed reference),
  `neuer_lieferant`, `neuer_preis` (append-only price row), `neue_formel`,
  `aendere_formel`, `neue_stammdaten_variable`, `aendere_stammdaten_wert` (rate change),
  `neue_ausfuehrungsart`, `neue_betriebsart`/`-kategorie`,
  `bauverfahren_zu_leistung` (mapping supersede), `entwurf_verwerfen`.
  All are thin wrappers producing single-entity (or minimal) `RezeptBundle`s through the
  existing `KatalogService` — validation, lifecycle, atomic activation, auto-reload all
  come for free.
- **Formula authoring rules:** vocabulary-first instruction; structured escalation
  `benoetigte_funktionen: [{name, zweck, beispiel_aufruf}]` when the math is not
  expressible (draft waits in `entwurf` until the function ships); validator polish —
  Rule 1 distinguishes *unbekannte Funktion* from *unbekannte Variable* (a `Name` that is
  a `Call` target).
- **Confirm gate — draft-first, NO graph interrupt.** A write tool validates and saves the
  bundle draft (`status=entwurf`); the agent's turn ends normally with the draft summary;
  the UI renders a confirm card from the draft; confirming calls
  `POST /katalog/bundle/{uuid}/aktivieren`, discarding `…/verwerfen`. The durable draft row
  IS the pause — it survives restarts, spans sessions, and needs no checkpointer or resume
  protocol. Interrupt gates remain right only where state is mid-graph (calculator, likely
  the Phase-3 compiler).
- `DEFAULT_USER`/`DEFAULT_AUTOR` remains the recorded author until auth lands.

### Lohn & Personal (roadmap)

Today: ONE flat rate (`stundenlohn_eur` = 42,00 €/h, KONSTANTE); crew sizes via the kontext
variable `anzahl_arbeiter` (default 2) and per-operation Kolonnen-KONSTANTEN
(`asphalt_kolonne` 6, `handeinbau_kolonne` 5, `gussasphalt_kolonne` 5, `dsk_kolonne` 4,
`grid_kolonne` 4); every Lohn-Formel is `stunden × stundenlohn_eur × besetzung`. No
Lohngruppen, no Mittellohn, no lohngebundene Kosten, no tariff validity.

- **Stufe 1 (pure data, authored with Phase-2 tools, zero engine change):** BRTV-Lohngruppen
  as Stammdaten variables (`lohn_lg2_eur` … `lohn_lg6_eur`) and **Mittellohn as a Formel**
  (weighted crew average + Zuschlagfaktor for lohngebundene Kosten). Fully expressible in
  the existing DSL vocabulary.
- **Stufe 2 (own entity, later):** a `Lohngruppe`/Personal catalog entity with temporal
  validity like prices (tariff rounds), plus a Kolonnen-Besetzung (`{lohngruppe: anzahl}`)
  per Geräteklasse/Ausführungsart from which the Mittellohn derives. Structurally analogous
  to Maschinen; own table, own tools, own review round.

Phase-1 reads already cover the status quo (rates via T27/T28, Lohn formulas via T26/T29).

## 7. Phase 3 — Recipe compiler (pointer only)

Discovery through the Phase-1 tools (the agent searches before it mints — reuse pressure by
prompt + the `wiederverwendung`/`neu` justification envelope), full multi-entity
`RezeptBundle` output, Phase-2 write path, eval treadmill (compile → validate → calculate →
judge; reuse rate as the core metric). Own plan document when Phases 1–2 are reviewed.

## 8. Open questions (answers wanted during THIS review)

1. **RESOLVED (2026-07-04):** Facet A = „**Geräteklasse**" (the Ausführungsart slot),
   Facet B = „**Betriebsarten**". Technical names/codes unchanged (§1.6).
2. **RESOLVED (2026-07-05):** reads default to `aktiv` only — answers are statements about
   what is true for calculations right now. Drafts appear ONLY on explicit request (T33, or
   `status="entwurf"` on a list tool). No proactive draft hints in ordinary answers; the
   user asks explicitly when they want the pending view.
3. **RESOLVED (2026-07-05):** price tools default `stichtag` = today. The engine's fixed
   `STICHTAG` in `store.py` stays a calculation concern.
4. **RESOLVED (2026-07-05):** keep both T21 (ranked convenience) and T24 (raw rows /
   history).
5. **RESOLVED (2026-07-05):** tool list T1–T33 confirmed complete by Arthur.

## 9. Non-goals

- No MCP (internal plumbing stays function calls; MCP only ever as a future external surface).
- No mutations in Phase 1 — not even "safe" ones.
- No DSL function authoring through any phase (engineering change, stated invariant).
- No catalog browser UI; chat-first. No changes to the calculator graph or the engine.
- No embedding/vector search in v1 — BM25/substring suffices for this vocabulary.

## 10. Phase 1 acceptance criteria

1. Every tool T1–T33 implemented in `lese_modell.py` with a unit test per tool (shape +
   one relationship assertion each against seeded data).
2. The canonical question set answers end-to-end through the agent (integration test with
   scripted tool-call assertions; LLM mocked): the ten questions embedded in §3's
   *Beantwortet* lines, including „Welche Lieferanten können AC 22 T S liefern?".
3. Truncation is never silent (`treffer_gesamt` asserted on a >limit listing).
4. T26 renders LaTeX + legend for a multi-input formula (snapshot test on the walker).
5. Read-only guarantee: the katalog_chat service imports no write surface
   (`entwurf_speichern`/`aktiviere` unreachable; asserted by a simple import-graph test).
6. `uv run pytest` green; `npm run gen:types` clean; UI build green.

## 11. Execution order (Phase 1)

0. All §8 questions are RESOLVED above; §3 is the reviewed, binding tool list.
1. `lese_modell.py` — all T1–T33 read functions + one unit test each (shape + one
   relationship assertion, against seeded test data; §10.1).
2. DSL→LaTeX walker + symbol legend (`kalkulation_v2/formel_darstellung.py`) + snapshot
   test (§10.4).
3. Tool schemas + thin handlers; `katalog_chat` service on `create_agent` per §5;
   `PromptType.KATALOG_CHAT` registration (follow `ADDING_A_PROMPT_TYPE.md` — conversation
   discriminator, no .prompt file).
4. `run_turn` wiring, SSE relay, UI entry point for a Katalog-Chat conversation;
   `npm run gen:types`.
5. Integration: the canonical question set with a scripted/mocked LLM (§10.2); read-only
   import-graph test (§10.5); truncation test (§10.3).

Work on a feature branch. Steps 1–2 are independent of 3–5 and can land first.
