# Strassenbau-Baukalkulation — Architecture & StateGraph Integration

A metadata-driven cost-estimation engine for German road-construction tenders
(EKT / Einzelkosten der Teilleistungen). It turns a Leistungsverzeichnis (LV)
position into an auditable unit price by selecting a construction method and
resolving every cost-driving variable through an ordered cascade of sources —
LV text, RAG, human, master data, formula, constant.

---

## 1. The core idea

A bid is built bottom-up from a strict four-level **catalog spine**, plus a
**variable/resolution layer** that feeds it numbers:

```
Leistung        the WHAT — the service (STLB-style), a leaf. Carries no method.
   │  (selected at runtime, not owned)
Bauverfahren    the recipe — an ordered list of Vorgänge. The HOW at a high level.
   │
Vorgang         one operation (mill, lay, compact …). Binds its Ausführungsart.
   │
Ausführungsart  HOW the operation is done — which machine/crew.
```

The separation of **Leistung** (what) from **Bauverfahren** (how) is the load-bearing
design decision. One Leistung can be fulfilled by several candidate Bauverfahren;
the calculator _selects_ one based on machinery/access/context. This is why the
model absorbed ~12 distinct cost-driver patterns across 5 trades without the
engine or the spine changing once.

Each Vorgang doesn't embed cost logic — it carries a **Rechnung**: named quantity/
curve **Instanzen** plus, per **Kostenart** (Material, Maschine, Antransport,
Abtransport, Entsorgung, Lohn), one or more cost lines. Every Instanz/cost line
**instantiates a base formula** (§1a). So the engine is the only compiled part; the
catalog, rates, and formula instantiations are **data**.

**Determinism & money:** all quantity/money math is `Decimal`, pure functions,
with cycle detection. The same inputs always produce the same EKT — essential
for reproducible, auditable bids.

---

## 1a. The base-formula redesign (2026-07)

The formula layer was reshaped from **174 recipe-specific formulas / 318 variables**
into **~16 parameterized base formulas** (Appendix A of `REZEPT_REDESIGN_PLAN.md`)
that every Vorgang instantiates. The model:

- **Base formula (`Formel`)** — one DSL expression over **declared formal parameters**
  (`FormelParameter`: `name`, canonical `einheit`, mandatory `beschreibung`, optional
  `standard`), written once in canonical units (m, m², m³, t, h, €, St, l, km). The
  16 cover the whole catalog: `F_STUNDEN`, `F_LOHN`, `F_MASCHINE`, `F_KOSTEN_SATZ`,
  `F_TRANSPORT`, the Mengengerüst (`F_MENGE_VOLUMEN`, `F_VOLUMEN_FLAECHE`,
  `F_FLAECHE_VOLUMEN`, `F_VOLUMEN_QUADER`, `F_MENGE_ANSATZ`, `F_ARBEITSMENGE`,
  `F_LAGEN`), and the curves/selections (`F_LEISTUNG_TIEFE`, `F_LEISTUNG_ERSCHWERT`,
  `F_UEBERGAENGE`, `F_STAFFEL`).
- **Instantiation (`FormelInstanz`)** — a Vorgang applies a base formula by **binding**
  its parameters to source paths: `kontext.<var>`, `stammdaten.<var>`,
  `baustoff.<feld>`, `formel.<instanz>` (a sibling instance), or a numeric literal.
  A polymorphic parameter (`einheit=None`) can be pinned with `einheiten`. Unit
  scaling (cm→m, kg→t) happens **at the binding seam** (`einheiten.py`), never inside
  an expression; a dimension change (m³→t) is a Mengengerüst formula, not a binding.
- **`VorgangRechnung`** — `instanzen: {name → FormelInstanz}` (named quantities/curves)
  plus `kosten: {Kostenart → [FormelInstanz]}` (the cost lines). `Vorgang.kalkuliere`
  evaluates the cost lines, recording each Instanz Vorgang-scoped (`V_X::name`) with
  provenance — the EKT audit trail is unchanged in shape.
- **Formeln are no longer variables.** There is no `FORMEL` resolution method for a
  variable and no `FORMEL_VARIABLEN`; the surviving variables are only `stammdaten`
  (rates + Baustoff bridges) and `kontext` (situational inputs incl. the geometry
  placeholders `flaeche_m2`/`menge_t`).
- **Prose + enforcement (the ontology).** Every base formula, parameter and variable
  carries retrieval-grade `beschreibung`; `katalog/ontologie.py` adds the binding-path
  grammar and an AST canonicalization. Bundle validation (`katalog/validierung.py`)
  makes prose mandatory, checks binding-path + **einheit compatibility**, and rejects a
  candidate formula **structurally isomorphic** to a base formula ("instantiate, don't
  mint"). The recipe compiler retrieves over the prose via the `ontologie_lookup` tool.

---

## 2. The engine — `model.py`

The one compiled artifact. No project dependencies (pydantic + stdlib). Every
other module imports from it. Key contents:

**Enums**

- `AufloesungsMethode` — `LANGTEXT, RAG, HITL, STAMMDATEN, KONSTANTE` (the `FORMEL`
  member is retained only to parse pre-redesign archived rows — variables are no
  longer produced by formulas). The first three are filled by the agent/human
  **before** calc; `STAMMDATEN/KONSTANTE` are computed **by** the calc.
- `Kostenart` — `MATERIAL, MASCHINE, ANTRANSPORT, ABTRANSPORT, ENTSORGUNG, LOHN`.
  The cost-line buckets a Vorgang produces.
- `Datentyp` — dezimal/ganzzahl/text/bool (mostly informational).

**Variable & resolution model**

- `AufloesungsSchritt` — one step in a cascade: `methode`, optional `prompt`
  (LLM instruction for LANGTEXT/RAG), `konfidenz_schwelle`, `stammdaten_pfad`
  (e.g. `"baustoff.rohdichte_t_pro_m3"`), `konstante`.
- `VariableDefinition` — a managed variable: `name`, `bezeichnung`, `beschreibung`,
  `einheit`, and an ordered `aufloesung: list[AufloesungsSchritt]`.
- `Formel` / `FormelParameter` — a **base formula** (§1a): `ausdruck` over declared
  `parameter`, `einheit`, `beschreibung`; `eingaben()` (parses referenced parameter
  names), `validieren()` (closure over the declared signature).
- `FormelInstanz` / `VorgangRechnung` — an instantiation (base formula + `bindung`)
  and a Vorgang's set of them (§1a).
- `VariablenWert` — a **resolved** value with provenance: `wert`, `quelle`
  (which AufloesungsMethode produced it), `konfidenz`, `beleg` (evidence snippet
  or master-data path). **This is the audit record.**

**Master-data model**

- `Baustoff` (material: kategorie, körnung, density, base price …),
  `Baustofflieferant` (supplier: standort, lat/lon, price list, `preis_fuer()`),
  `BaustoffPreis`.

**Runtime**

- `Kalkulationskontext` — per-position state: `werte` (dict of resolved
  VariablenWert — **filled by the StateGraph and by the calc**), `stammdaten`
  (e.g. `{"baustoff": <Baustoff>}`), `stichtag`.
- `eval_ausdruck(ausdruck, resolver)` — the formula DSL evaluator. Restricted
  Python AST: arithmetic, power, unary, comparison, BoolOp, **IfExp (ternary)**,
  and whitelisted functions `abs/min/max/round/ceil/floor`. All `Decimal`.
  (Production swap candidate: `simpleeval`/`asteval`.)
- `Kalkulator.resolve(name, ctx, …)` — **the heart of the system.** Resolution
  order:
  1. memo (already computed this calc)
  2. cycle check (raises on cyclic formulas)
  3. **`ctx.werte` — if the value is already there, return it.** This is the
     seam: the StateGraph pre-fills LANGTEXT/RAG/HITL values here.
  4. otherwise walk the variable's `aufloesung` steps and act on
     `STAMMDATEN` (lookup in `ctx.stammdaten`), `KONSTANTE` (return the fixed
     value). **`LANGTEXT/RAG/HITL` steps are skipped at calc time** — reaching one
     means the agent never supplied a value → raises `"… nicht auflösbar → HITL"`.
     (Variables no longer resolve `FORMEL`; computation lives on the Vorgang
     Rechnung, not the variable.)
- `Vorgang.kalkuliere(kalk, ctx)` — evaluates the `rechnung` cost lines per
  Kostenart (each a `FormelInstanz`: resolves its bindings through `Kalkulator`,
  scales units at the seam, evaluates the base formula), returns the cost lines
  with provenance + the Vorgang EKT. A named Instanz materializing a booked
  variable (e.g. `menge_t`) is short-circuited by `ctx.werte`.

**Legacy cruft to delete on integration:** the bottom of this file
(`_input_var`, `baue_katalog`, `baue_kontext`, `drucke`, `demo`) is the
**original monolithic demo** that predates the decomposition. The live system is
`Store.py` + the separate catalog modules. Note there are **two** `baue_kontext`
functions (this vestigial one and the real one in `Store.py`) — keep only
`Store.py`'s.

---

## 3. The catalog spine

Each file is an authored, static catalog. Design intent: **each file ≈ one
future Postgres table**; string keys between files are unenforced foreign keys.

### `ausfuehrungsarten.py`

Exports `AUSFUEHRUNGSARTEN` (dict key → `Ausführungsart`). The machine/crew
configurations (Bagger, Kaltfräse, Walze, Bankettwalze, Fertiger, Beschicker,
Rampenspritzgerät, HD-Wasch-Sauganlage, …). Depends only on `model`.

### `vorgaenge.py`

Exports `VORGAENGE` (key → `Vorgang`). Each Vorgang binds an Ausführungsart and
carries a `rechnung` of base-formula instantiations (§1a). The atomic operations
(fräsen, schneiden, FSS legen/profilieren/verdichten, asphalt einbau, anspritzen,
naht, …). Depends on `model`, `ausfuehrungsarten`, `formel`, `einheiten`.

### `bauverfahren.py`

Exports `BAUVERFAHREN` (key → `Bauverfahren`). **Static, authored** recipes —
each lists its Vorgänge by key via the `_bv(code, name, *vorgang_keys)` helper.
A recipe can chain several Vorgänge (e.g. FSS = legen + profilieren + verdichten).
Depends on `model`, `vorgaenge`. (Earlier this was wrongly derived 1:1 from
VORGAENGE; it is now hand-authored.)

### `leistungen.py`

Exports `LEISTUNGEN` (code → `Leistung`). **Leaf** services: code, name,
`einheit`, optional `standard_kennung` (STLB/STL-Nr). No method reference.
Depends only on `model`.

### `leistung_bauverfahren.py` — the selection seam

Exports `LEISTUNG_BAUVERFAHREN` (leistung_code → ordered list of candidate
bauverfahren keys, first = default), plus:

- `kandidaten(leistung_key)` — the candidate set.
- `waehle_bauverfahren(leistung_key, praeferenz=None)` — honours a valid
  preference, else returns the default. **This is the StateGraph's "decide on a
  recipe" hook.**
- `validate()` — runs at import; raises if any Leistung has no candidate or a
  candidate names a non-existent Bauverfahren.

Depends on `leistungen`, `bauverfahren`. Most Leistungen have one candidate;
multi-candidate cases (e.g. FSS grader-train vs fertiger; aufbrechen vs fräsen)
are where method selection becomes a real decision.

---

## 4. The variable / formula layer

These three modules populate the **catalog of variables** the spine references.
They are merged in `Store.py` into one `KATALOG`.

### `stammdaten.py`

Exports `STAMMDATEN_VARIABLEN`. The **rate book**: `KONSTANTE` variables (fuel,
wages, machine €/h, productivities, disposal rates, …) via `konst(...)`, plus a
few `STAMMDATEN` bridge variables that read master-data fields (e.g.
`dichte_t_pro_m3` ← `baustoff.rohdichte_t_pro_m3`). Depends on `model`.
**Almost every number here is a flagged placeholder.**

### `kontext_variablen.py`

Exports `KONTEXT_VARIABLEN`. The **situational inputs** with their cascades.
Helpers:

- `eingabe(name, bez, einheit, rag_prompt)` → cascade `LANGTEXT → RAG → HITL`
  (extracted from the LV).
- `geometrie(name, einheit)` → filled from the LV `menge` (HITL fallback).
- `mit_default(name, …, default, erststufe)` → an input with a `KONSTANTE`
  fallback so calc still runs unattended.
- Custom definitions for high-stakes variables (e.g. `fraesgut_klasse` uses
  `RAG → HITL` with **no** constant fallback and a high confidence threshold —
  see §7).

Depends on `model`. `flaeche_m2` and `menge_t` are ordinary geometry placeholders
here: booked directly when the position bills in that unit, else materialized by a
Vorgang Instanz (`F_FLAECHE_VOLUMEN` / the asphalt-tonnage chain in `vorgaenge.py`)
whose `variable` seam a booked value short-circuits.

### `formel.py`

Exports `FORMELN` (name → `Formel`) — the **~16 base formulas** (§1a), each declaring
its parameters in canonical units, import-time validated. No `FORMEL_VARIABLEN`
(formulas are not variables). The `_basis(name, ausdruck, einheit, beschreibung,
parameter)` helper builds and validates one. Depends on `model`, `einheiten`.

> **Catalog merge (in `Store.py`):**
> `KATALOG = {**STAMMDATEN_VARIABLEN, **KONTEXT_VARIABLEN}` — two sources, no key
> overlaps. The old `FORMEL_VARIABLEN` layer is gone; computed quantities live as
> Vorgang Instanzen, not variables. A booked geometry value still short-circuits its
> derivation because `ctx.werte` is checked first in `resolve` / `_instanz_wert`.

---

## 5. Materials & suppliers (master data)

### `lieferanten.py`

Exports `LIEFERANTEN` (52 fictional suppliers at **real, geocodable** German
towns with lat/lon), plus `haversine_km`, `entfernung_km` (×1.3 detour factor),
`naechste_lieferanten`. Depends on `model`. **Caveat in-file:** coordinates are
~1–3 km accurate; the `standort` address string is the authoritative geocoding
key; haversine ≠ road distance (swap in OSRM/Google for production).

### `materialien.py`

Exports `BAUSTOFFE` (26 canonical `Baustoff`: FSS, STS, mineral mixes, asphalt
mixes, bitumen, soils) and category groupings. `bestuecke()` gives each supplier
a type-appropriate assortment; `guenstigster_lieferant()` = cheapest delivered
(price + transport × distance). Depends on `model`, `lieferanten`. The single
source of truth for materials.

### `lieferanten_preise.py`

Exports `PREISE` — a **static** flat join table of
`(lieferant_code, baustoff_code, preis_eur_pro_t)` (515 rows, hand-editable, no
runtime RNG), and `lade_preise(...)` which attaches them to supplier objects.
Depends on `model`. This is the future supplier-price table.

> **Known gap:** asphalt mixes and bitumen emulsion are currently priced by
> per-position `materialpreis_eur_pro_t` / `asphalt_preis_eur_pro_t` overrides,
> **not** routed through this master-data path. Since asphalt is 86–93 % of its
> positions' cost, wiring mixes/emulsion in as proper Baustoffe with supplier
> prices is the highest-value calibration step.

---

## 6. Positions & assembler

### `positionen.py`

Defines the `Position` model — `oz`, `leistung_key` (→ LEISTUNGEN),
**optional** `bauverfahren_key` (override; default None ⇒ use the mapping's
default candidate), `menge`, `baustoff_code`, `kontext` (dict of extracted
context values). Exports `POSITIONEN` — the 41-position fixture (a real
Landesstraße L 101 mill-and-fill). In production the StateGraph builds Position
objects; this fixture stands in for "what the agent will have extracted."

### `Store.py` — the assembler & entry point

Imports everything, builds `KATALOG` (the merge above) and `FORMELN`, and
exposes:

- `_GEOM = {"m2":"flaeche_m2","m":"laenge_m","m3":"volumen_m3","t":"menge_t"}` —
  maps a position's Einheit to the geometry variable booked from `menge`.
- `baue_kontext(pos, einheit)` — builds a `Kalkulationskontext`: books the
  geometry value, attaches the Baustoff to `stammdaten`, and pre-fills the
  position's `kontext` values into `ctx.werte` (tagged with quelle). **This is
  the stand-in for the StateGraph's resolution output.**
- `kalkuliere(pos)` — selects the Bauverfahren (`waehle_bauverfahren`), iterates
  its Vorgänge, sums EKT, returns unit price + full cost-line detail with
  provenance.
- `build_store()` and a `__main__` that prints the whole-section EKT table.

Depends on **all** modules.

---

## 7. Running it as a chat-embedded LangGraph StateGraph

The calculation is **not** a standalone graph — it is a command inside the
existing per-position chat agent. Each position already has a "Chat about
Position" turn-processor carrying the LV `kurztext/langtext/hinweise/menge/
einheit` as permanent context, with the hybrid BM25/semantic RAG corpus wired
in. "Let's calculate this position" launches a calculation **subgraph that
inherits the chat transcript as state**, streams its reasoning back into the
_same_ chat via the existing reasoning-output mechanism, and pauses for human
review before computing. Scope is **per-position**: there is no project-level
shared context yet (see the cross-position note in §9).

The engine's split still holds — `LANGTEXT/RAG/HITL` are the agent's job (fill
`ctx.werte`), `FORMEL/STAMMDATEN/KONSTANTE` are the calc's — but the agent phase
gains a **chat-precedence source above the catalog cascade** and a **mandatory
human-confirmation gate below it**, and the _method_ (Leistung + Bauverfahren)
is itself a confirmed decision, not an automatic one.

### Resolution precedence (per variable)

The catalog's `aufloesung` cascade is the _playbook_ the graph follows, wrapped
by chat-precedence on top and human review at the bottom:

```
0. CHAT      already stated by the user pre-launch → take it, skip ALL searching
1. LANGTEXT  extract from LV langtext/hinweise   (prompt from the prompt library)
2. RAG       query the document corpus           (existing RAG graph; rag_prompt = intent)
3. DEFAULT   mit_default KONSTANTE fallback, flagged as a default
── propose, then review ──
4. REVIEW    EVERY variable shown with proposed value + provenance; accept or override
5. CONFIRM   final confirmation of the full set → write to ctx.werte → compute
```

Source 0 is the key behavioral rule: if the user said "die Fräsgutklasse ist
pechhaltig" earlier in the chat, that variable is resolved from the transcript
(`quelle = HITL`, `beleg =` the chat snippet) and **no langtext scan or RAG query
runs for it**. Steps 1–3 run only for variables the chat did not already pin.

### Two human gates

**Gate A — Method review (HITL interrupt).** After classification the graph
proposes the `leistung_key` and the candidate Bauverfahren (default highlighted),
and the user **confirms the Leistung and selects the Bauverfahren**. Recipe
selection is a real decision: for multi-candidate Leistungen (FSS grader-train vs
fertiger; aufbrechen vs mill-out) the choice can move the price more than any
single variable. _This gate must precede variable resolution_, because the
required-variable worklist is derived from the chosen recipe — correcting the
Leistung re-derives the candidate set, and changing the recipe re-derives the
worklist.

**Gate B — Variable review + confirm (HITL interrupt).** Every variable the calc
will consume is presented for accept/override; the submit _is_ the final
confirmation, after which compute proceeds.

**What "every variable" means — and why rates are included.** The worklist is not
just the extracted inputs. `benoetigte_variablen` (`worklist.py`) walks the chosen
recipe's Vorgänge → `rechnung` instanzen → binding paths down to **every resolution
leaf** (`kontext.*`/`stammdaten.*` variables; `formel.<instanz>` references are walked
through, literals and `baustoff.*` fields are not variables). Those leaves fall into
three kinds, all overridable in the review:

- **Extrahierte Eingaben** (kontext inputs, source CHAT/LANGTEXT/RAG/DEFAULT) —
  carry extraction confidence.
- **Sätze** (the `KONSTANTE` rate book — €/h, productivities, disposal rates) —
  catalog values, no extraction confidence.
- **Stammdaten** (`STAMMDATEN` lookups — densities, supplier prices) — master
  data.

Vorgang Instanzen (the computed intermediates) are _not_ in the review (they are
derived) but _are_ in the output transparency table.

### Confidence-tiered presentation (configurable)

Showing all ~6–40 leaves with equal weight every time trains banner-blindness,
and the one variable where review actually matters (`fraesgut_klasse`, a ~€226k
swing) gets the same reflexive "accept" as the layer thickness. So the review is
**complete but tiered** by a configurable threshold:

- `konfidenz_schwelle_review` — **default 0.75.**
- Extracted inputs with `konfidenz < 0.75` → **surfaced for an explicit
  decision**, visually flagged.
- Extracted inputs ≥ 0.75, plus **all rates and stammdaten** (no extraction
  uncertainty) → **pre-accepted in a collapsed tier**, still overridable on
  expand.
- Variables marked high-stakes (e.g. those with no `KONSTANTE` fallback, like
  `fraesgut_klasse`) → **always surfaced**, regardless of confidence.

Net: every value is present and overridable (honoring "rates in the review");
attention is spent only where extraction is uncertain or money is asymmetric.

### The state object

The graph state is the **chat + calc envelope**; the resolved-values dict is its
heart but not its whole. (Single-level, per-position — no bid-level layer yet.)

```python
class PositionKalkulationState(TypedDict):
    # — permanent LV context (from the chat agent) —
    oz: str; kurztext: str; langtext: str; hinweise: str
    menge: Decimal; einheit: str; stl_nr: str | None
    chat_verlauf: list[Message]              # pre-launch transcript = precedence source 0

    # — config —
    konfidenz_schwelle_review: float         # default 0.75

    # — method decision (Gate A) —
    leistung_key: str | None                 # classification node, user-confirmable
    bauverfahren_kandidaten: list[str]        # from kandidaten(leistung_key)
    bauverfahren_key: str | None             # user-selected

    # — resolution worklist (derived AFTER the recipe is confirmed) —
    benoetigte_variablen: list[str]          # ALL formula-tree leaves: inputs + rates + stammdaten
    kandidaten: dict[str, VariablenWert]     # proposed values + provenance, pre-review
    review_status: dict[str, Literal["vorgeschlagen","akzeptiert","ueberschrieben"]]
    review_tier: dict[str, Literal["surfaced","collapsed"]]
    hitl_offen: list[HITLFrage]              # what the current interrupt is waiting on

    # — outputs —
    werte: dict[str, VariablenWert]          # confirmed → becomes Kalkulationskontext.werte
    ekt_zeile: EKTRow | None
    beschreibung: str | None                 # long-form narration
    nachweis_tabelle: list[NachweisZeile] | None   # the transparency table
    reasoning: list[str]                     # streamed via the existing mechanism
    warnungen: list[str]                     # unit-sanity, low-confidence, feasibility
```

Clean seam: `werte` is exactly what the calc consumes. At the compute node build
`Kalkulationskontext(werte=state["werte"], stammdaten=…, stichtag=…)` and call
`kalkuliere`. **Do not make the state literally a `Kalkulationskontext`** — that
model stays the calc's concern; the state is the superset that produces it.

### Graph nodes (each streams reasoning into the chat)

1. **launch** — seed state from the chat agent's LV context + transcript.
2. **extract_chat_values** — one LLM pass over `chat_verlauf` to harvest values
   the user already stated (source 0), including any method preference; lock them.
3. **classify_leistung** — map position → `leistung_key` using a **classification
   prompt from the prompt library** (the new prompt-type to add: prompt-type,
   system text, model, temperature, top_p). Langtext is authoritative; ignore
   boilerplate bled into Hinweise.
4. **method_review** — _Gate A_ interrupt: confirm Leistung, select Bauverfahren
   from `kandidaten(leistung_key)`. (Correcting Leistung re-runs 3→4; a different
   recipe re-runs 5.)
5. **derive_required_variables** — walk the confirmed recipe's formula tree to all
   leaves → `benoetigte_variablen`. _Graph topology is identical for every
   position; the worklist is data-derived, never hardcoded._
6. **resolve_variables** — for each leaf not chat-pinned: extracted inputs run the
   cascade (LANGTEXT prompt from library → RAG via the existing corpus graph with
   `rag_prompt` as intent → DEFAULT); rates/stammdaten are catalog lookups. Each
   yields a candidate `VariablenWert` with confidence + `beleg`; set `review_tier`
   from the threshold + high-stakes flags.
7. **variable_review** — _Gate B_ interrupt: surfaced tier shown for decision,
   collapsed tier available on expand; accept/override each; submit confirms the
   full set → write `werte`.
8. **compute** — build the context, call `kalkuliere`. Deterministic.
9. **render_output** — emit the three artifacts below.

### Output artifacts

`kalkuliere` returns the EKT plus per-cost-line provenance, and the transparency
table **falls out of the resolver for free**: after a full calc, `ctx.werte`
holds _every_ variable touched — confirmed inputs, `STAMMDATEN` lookups,
`KONSTANTE` rates, and every `FORMEL` intermediate — each tagged `quelle`/`beleg`.

- **EKT row** — unit price + GP for the position list.
- **Long-form description** — an LLM narration (prompt from the library) over the
  result + `ctx.werte`: which recipe, why, the cost-line story.
- **Nachweistabelle (the important one)** — render `ctx.werte`: per entry
  `name · wert · einheit · quelle · beleg`, and for a Vorgang Instanz
  (`V_X::name`, `quelle=FORMEL`) also the base formula (`beleg`) and its bindings.
  The full derivation tree — the estimator sees exactly how the EKT was built,
  input by input,
  formula by formula, source by source.

### Integration touchpoints (existing systems)

- **Reasoning stream** — reuse as-is; every node narrates ("Leistung klassifiziert
  als …", "tiefe_cm aus Langtext: 4 cm (Konfidenz 0.82)", "Fräsgutklasse nicht im
  Langtext → RAG im Schadstoffgutachten …").
- **Prompt library** — extend with new prompt-types (each storing system text +
  model + temperature + top_p): Leistung classification, langtext extraction (one
  generic extractor parameterized by the variable's `bezeichnung`/`prompt`, or
  per-variable), and the output narration.
- **RAG graph** — `resolve_variables`' RAG step calls the existing hybrid graph,
  passing the variable's catalog `rag_prompt` as retrieval intent; the answer + its
  source snippet become the candidate's `wert` + `beleg`.
- **HITL Gates** - since the primary interface is a ReactJS chat-based UI, we can use custom
  written React components to render the decision/edit gates in the UI. I prefer this
  approach to a text-only chat-based HITL gate.

## 8. Dependency graph (import order)

```
model.py                      (no project deps)
  ├── einheiten.py             → the binding-seam unit converter
  ├── lieferanten.py
  │     └── materialien.py
  ├── lieferanten_preise.py
  ├── stammdaten.py            → STAMMDATEN_VARIABLEN
  ├── kontext_variablen.py     → KONTEXT_VARIABLEN
  ├── formel.py                → FORMELN (~16 base formulas)
  ├── ausfuehrungsarten.py     → AUSFUEHRUNGSARTEN
  │     └── vorgaenge.py       → VORGAENGE (instantiate base formulas)
  │           └── bauverfahren.py → BAUVERFAHREN
  ├── leistungen.py            → LEISTUNGEN
  │     └── leistung_bauverfahren.py (+ bauverfahren) → waehle_bauverfahren
  └── positionen.py            → Position, POSITIONEN
Store.py  imports ALL of the above (assembler/entry point)
```

---

## 9. Integration checklist for Claude Code

1. Delete the legacy `baue_katalog`/`baue_kontext`/`demo` block from `model.py`.
2. Treat `Store.py`'s `KATALOG`/`FORMELN`/`baue_kontext`/`kalkuliere` as the
   live API the StateGraph calls.
3. Replace the `POSITIONEN` fixture with StateGraph-built `Position` objects.
4. The StateGraph fills `ctx.werte` (LANGTEXT/RAG/HITL) **before** calling
   `kalkuliere`; the resolver does the rest deterministically.
5. Carry `VariablenWert.{quelle, konfidenz, beleg}` through to the chat/output
   layer — that is the audit trail and the review trigger.
6. The calculation subgraph is launched from the existing per-position chat
   ("let's calculate this position"), inherits `chat_verlauf` as precedence
   source 0, and streams reasoning via the existing mechanism (§7).
7. Extend the prompt library with the new prompt-types (Leistung classification,
   langtext extraction, output narration); wire the existing hybrid RAG graph
   into `resolve_variables`.
8. Two human gates: method review (Leistung + Bauverfahren) then variable review
   (all leaves, tiered by `konfidenz_schwelle_review`, default 0.75; rates and
   stammdaten overridable but collapsed by default).
9. Output three artifacts: EKT row, long-form description, and the
   Nachweistabelle rendered from `ctx.werte` (the derivation tree with
   provenance).
