# Katalog Agent Phase 3 Plan — the Recipe Compiler

The final phase of `KATALOG_AGENT_PLAN.md`: **NL Construction German → a full multi-entity
`KatalogBundle`** (Leistung + Bauverfahren + Vorgänge + Formeln + Variablen + Mapping), authored
conversationally, reviewed on the confirm card, activated by the human, immediately calculable.

Execution mode differs from Phases 1–2: **Fable builds the first iteration interactively** (prompt
design, tool ergonomics, and eval judgment interlock too tightly for spec-then-handoff); this doc
fixes the decisions, the scope, and the eval set — the parts that must survive the interaction.

---

## 1. Decisions

- **D1 — The compiler is the katalog_chat agent plus ONE tool.** No separate program: the agent
  discovers with the T-tools (suche/zeige/erklaere/verwendung — built precisely for this), then
  emits the recipe through a new write tool **W18 `rezept_entwurf_speichern`** (full
  `KatalogBundle` + justification envelope, §3). Validation errors return as tool results and the
  agent repairs agentically in its existing loop. Draft-first confirm, activation human-only —
  all Phase-2 machinery unchanged.
- **D2 — The Part-B harness is retired.** `rezept_autor/` (graph, prompts, run_service), the
  `rezept_review` interrupt stage in `InterruptPanel.tsx`, its UI entry point and
  `_rezept_events` routing are **deleted** — their ideas (validation-repair, structured review)
  survive in stronger forms. Exception: the `PromptType.REZEPT_AUTOR` enum member and its DB
  CHECK value stay (historical conversation rows must remain parseable); `run_turn` treats such
  conversations as not continuable. Mark the member `# retired — kept for historical rows`.
- **D3 — Reuse policy (final, per Arthur):**
  - **Strong reuse pressure:** Vorgänge, Ausführungsarten/Geräteklassen, Stammdaten rates.
    Prompt-enforced ("erst suchen, dann münzen; jeder neue Code wird begründet") + the
    near-duplicate warning (§4).
  - **Calibrated for Betriebsarten:** the same physical operation on different material is a
    DIFFERENT Betriebsart when the operating profile genuinely differs (compacting FSS vs.
    Asphalt: speed, water, passes — that difference is exactly what Betriebsarten exist to
    encode, via distinct Leistungsprofile). Mint when the *productivity/profile* differs;
    reuse when only the context differs.
  - **Free minting:** Formeln and Variablen (recipe-specific by nature).
- **D4 — Mengeneinheit `St` joins the engine geometry.** `store.GEOM` knows only
  `m2/m/m3/t`; one of the four eval recipes (R2) — and several of the most frequent LV
  families — are Stück-based. In scope: `GEOM["St"] = "anzahl_st"` + the `anzahl_st` kontext variable. NOT in
  scope: time/lump-sum units (`Std`, `d`, `Psch`, `Mt`, `h`) — the Vorhalte-/Baustelleneinrichtung
  families need a duration-cost model that is its own design (documented boundary, §8).
- **D5 — Escalation stays conversational** (Phase-2 D7 unchanged): an inexpressible formula
  persists nothing; the agent formulates the Entwicklerauftrag in chat.

## 2. The Formel-Editor question (Arthur's concern, answered)

NL→AST with LaTeX preview is the *authoring* path; a real Kalkulator/engineer will eventually
want **direct manipulation** — an editor over expressions and calculation groups. Position:

- **Everything below the UI already exists.** Formulas are text in a validated DSL; W8/W9 give
  create/edit-with-diff through drafts; `Formel.validieren` + the LaTeX walker give live
  validation/preview; `erklaere_variable` (T29) yields the derivation tree — which IS the
  "calculation group" structure (Vorgang → Kostenarten → Formeln → inputs); every save path
  converges on a `KatalogBundle` draft with human confirm. The stack was built so that chat,
  card, and any future visual editor are all just clients of the same write unit.
- **What a visual editor adds** is precision manipulation: a tree panel (T29 envelope rendered
  interactively), an expression field with live validate+LaTeX (needs one trivial endpoint:
  `POST /katalog/formel/vorschau` — validate an arbitrary `ausdruck` + return LaTeX, no write),
  and save-as-draft through the existing bundle path. React work plus one endpoint; zero engine
  or model work. The LLM remains useful *inside* the editor (inline NL→expression drafts).
- **Sequencing:** post-Phase-3, ideal Opus scope. Phase 3 forecloses nothing; the `vorschau`
  endpoint may land early if the card work wants it anyway.

## 3. W18 `rezept_entwurf_speichern` — the compiler tool

```
rezept_entwurf_speichern(
    bundle:            KatalogBundle,     # any subset; typically Leistung + BV + Vorgänge
                                          # + Formeln + Variablen + Mapping (+ Baustoffe)
    wiederverwendung:  [{code, warum}],   # every existing entity the recipe binds — justified
    neu:               [{code, warum_nicht_vorhanden}],  # every minted code — justified
)
```

- Validation = the full store rule set (R1–R9) — nothing weakened; nothing persists on failure;
  the error report returns to the agent for agentic repair.
- Envelope = the Phase-2 draft envelope + the justification lists + near-duplicate warnings (§4)
  + per-Formel LaTeX. The envelope is the confirm card's content AND the eval's measurement
  surface (reuse rate reads `wiederverwendung`/`neu` directly).
- The justification lists are validated for coverage: every code in the bundle appears in
  exactly one of the two lists (a mechanical check, not LLM trust).

## 4. Near-duplicate warning (reuse pressure, enforced softly)

At the W18 tool layer (not in `pruefe_bundle`): every minted Vorgang/Ausführungsart/Betriebsart/
Stammdaten-Variable is BM25-matched (the `suche_katalog` machinery) against the active catalog;
a high-similarity hit produces a warning naming the existing candidate — onto the envelope, onto
the card, judged by the human. Warnings never block.

## 5. Handbuch — the compiler section

Extends the write section: the recipe workflow is **verstehen → suchen (T-tools; never mint
before searching) → planen (reuse vs. mint per D3, justify both) → W18 → Karte**. Includes the
worked-example framing (one existing recipe shown description→bundle) and the D3 policy in
the agent's own words, including the Betriebsart calibration.

## 6. The eval set — four recipes from the real LV data

Mined from `lv_items` (1,147 Normalpositionen): the most frequent position families with NO
covering Leistung among the existing 31. Each: the real LV-Langtext (verbatim), the German
description a Kalkulator would give the compiler, and an English translation. These four are
the eval set and the demo material.

Deliberately excluded despite being the single most frequent uncovered family:
**Verkehrssicherung** (Schilder, Absperrung, Vorhalten — 40+ positions). Most German road
builders subcontract it (Nachunternehmerleistung), so it is not an EKT recipe family for the
compiler; its Vorhalte-positions would additionally need the time-unit cost model excluded
under D4.

### R1 — Bordstein aufnehmen (m) — linear demolition with sorting + disposal

**LV-Langtext (real, 16 m):**
> Bordstein aufnehmen. Bordstein = Tiefbordstein aus Beton, Höhe bis 30 cm. Fundament aus
> Beton, bis 10 cm dick, aufbrechen. Wiederverwendbare Bordsteine säubern, auf Paletten
> stapeln, innerhalb der Baustelle fördern und sortiert lagern. Aufbruchgut und nicht
> wiederverwendbare Bordsteine durch den AN einer Verwertung zuführen, AVV-Nr.: 170101,
> Entsorgung wird gesondert vergütet. Erforderliche Erdarbeiten ausführen, Boden im
> Aushubbereich verteilen.

**Kalkulator (DE):** „Tiefborde aufnehmen: Betonfundament mit dem Bagger aufstemmen, Bordsteine
aufnehmen — die brauchbaren säubern wir und stapeln sie auf Paletten, der Rest geht mit dem
Aufbruch zur Verwertung. Zwei Mann und ein Bagger, etwa 25 Meter die Stunde. Für die Entsorgung
rechnen wir Fundament plus Ausschuss mit rund 60 Kilo je Meter zum Betonaufbruch-Satz, dazu
Abtransport je Tonne und Kilometer zur Deponie."

**English:** "Taking up curbstones: break up the concrete foundation with the excavator, lift
the curbs — the reusable ones get cleaned and stacked on pallets, the rest goes to recycling
with the rubble. Two men and an excavator, about 25 meters per hour. For disposal we figure
foundation plus rejects at roughly 60 kilos per meter at the concrete-rubble rate, plus haulage
per tonne-kilometer to the tip."

*Expected reuse: `AA_BAGGER` (Geräteklasse), disposal/transport Stammdaten pattern
(`transport_eur_pro_t_km`, Entsorgungssätze), `anzahl_arbeiter`. Expected mints: the Leistung,
BV, Vorgang, Formeln (Stunden, Tonnage, Lohn/Maschine/Entsorgung/Abtransport), a
Betonaufbruch-Entsorgungssatz if none fits.*

### R2 — Schieberkappe auf Höhe setzen (St) — Stück-based street-fixture work ⚠ needs D4

**LV-Langtext (real, 1 St):**
> Schieberkappe des AG mit Deckel (nach DIN 4056), Gehäuse aus PA+, Deckel aus GJL, Bolzen und
> Steg aus Niro A2-70, höhenverstellbar. Schieberkappe zunächst provisorisch auflegen und
> entsprechend dem Bauablauf Zug um Zug bis auf planmäßige Höhe setzen. Oberflächen: in
> bituminöser Oberfläche.

**Kalkulator (DE):** „Schieberkappen regulieren: je Stück die Kappe freilegen, provisorisch
auflegen und beim Deckeneinbau Zug um Zug auf planmäßige Höhe setzen. Reine Handarbeit — zwei
Mann schaffen etwa vier Kappen die Stunde, kleines Gerät. Die höhenverstellbare Kappe stellt
der Auftraggeber; wir setzen je Stück fünf Euro Mörtel und Kleinmaterial an."

**English:** "Adjusting valve boxes to grade: per piece, expose the box, set it provisionally,
and bring it up to final level step by step as the surfacing goes in. Pure hand work — two men
manage about four boxes an hour, small tools. The height-adjustable box is supplied by the
client; we allow five euros per piece for mortar and sundries."

*Expected reuse: `AA_KOLONNE`, `stundenlohn_eur`. Mints: Leistung/BV/Vorgang, Formeln over
`anzahl_st` (D4), a Kleinmaterial-Konstante.*

### R3 — Risse im Fräs-Verguss-Verfahren sanieren (m) — linear crack repair

**LV-Langtext (real, 2.700 m, abridged):**
> Offene Längs-/Querrisse bzw. Längs-/Quernähte mittels Fräse auffräsen. Bei einer Rissbreite
> von 2 bis 12 mm: Fräsbreite 8–14 mm, Frästiefe 15–20 mm. […] Lose Teile entfernen sowie bei
> Nässe Fräsbereich trocknen. Rissflanken mit Voranstrichmittel anstreichen […]. Der Füllraum
> ist mit Spezialbitumen zu vergießen und danach unter Verwendung eines Ziehschuhes mit
> gleichem Material abzudecken (Fräs-Verguss-Verfahren).

**Kalkulator (DE):** „Rissanierung im Fräs-Verguss-Verfahren: Riss mit der kleinen Rissfräse
auffräsen, ausblasen und bei Nässe trocknen, Flanken vorstreichen, mit Spezialbitumen vergießen
und mit dem Ziehschuh abdecken. Trupp mit drei Mann und Vergusskocher, rund 60 Meter die
Stunde. Vergussmasse etwa 0,4 Kilo je Meter, Voranstrich rechnen wir pauschal je Meter."

**English:** "Crack repair by the mill-and-seal method: rout the crack with the small crack
router, blow it out and dry it if wet, prime the flanks, pour with special bitumen and cap it
with the drag shoe. Crew of three with the sealing kettle, around 60 meters an hour. Sealant
about 0.4 kilos per meter; primer we price flat per meter."

*Expected reuse: `laenge_m` geometry, Lohn pattern. Mints: a Rissfräse/Vergusskocher
Geräteklasse (nothing existing fits — justified mint), Betriebsart, Baustoff (Vergussmasse),
Formeln.*

### R4 — Schadstellen mit dem Thermocontainer sanieren (t) — tonnage-based patch repair

**LV-Langtext (real, 5 t, abridged):**
> Sanierung von Schadstellen mittels Asphaltthermocontainer AC 8 D N. Schadhafte Asphaltschicht
> mit Asphaltbeton AC 8 D N verschließen. Flächengrößen: 1,00 m² bis 8,00 m². Es sind alle
> notwendigen Arbeitsleistungen einschließlich Material, Geräte und Arbeitskräfte einzurechnen
> […] Entfernen des Asphalts durch Schneiden, Stemmen oder Fräsen, Säubern und Trocknen,
> Anspritzen mit Bitumenemulsion sowie Verdichten des Einbauasphalts.

**Kalkulator (DE):** „Schadstellensanierung mit dem Thermocontainer: Schadstelle ausschneiden
oder -fräsen, säubern, anspritzen, mit AC 8 D N aus dem Thermocontainer verfüllen und mit
Rüttelplatte oder kleiner Walze verdichten. Abgerechnet wird je eingebauter Tonne. Drei Mann
mit dem Thermocontainer auf dem Lkw, etwa anderthalb Tonnen die Stunde. Material frei Bau,
Emulsion anteilig, Fräsgut-Entsorgung anteilig je Tonne."

**English:** "Pothole/patch repair with the hotbox: cut or mill out the damaged area, clean it,
tack-coat it, fill with AC 8 D N from the hotbox and compact with a plate compactor or small
roller. Billed per tonne installed. Three men with the hotbox on the truck, about one and a
half tonnes an hour. Material delivered to site, emulsion pro-rata, milling-waste disposal
pro-rata per tonne."

*Expected reuse: `menge_t` geometry, Emulsion/Entsorgung/Transport-Stammdaten, possibly the
nearest AC-8 Baustoff (or a justified `AC 8 D N` mint). Mints: Thermocontainer-Geräteklasse,
Leistung/BV/Vorgang, Formeln.*

## 7. Eval loop

`server/scripts/eval_rezept_compiler.py`: for each of R1–R4 — feed the Kalkulator description
to the agent programmatically (real LLM, no SSE) → measure: (a) valid bundle produced + repair
iterations used, (b) reuse rate against the expected-reuse notes above, (c) activation in a
rolled-back transaction + calculation of a synthetic position (menge from the real LV row) —
EKT computes and is order-of-magnitude sane, (d) justification coverage. Output: a Markdown
report per run. Human-graded; no automated pass/fail thresholds in v1 — four recipes is a
judgment set, not a benchmark.

## 8. Scope

**In:** W18 + envelope + coverage check; near-duplicate warnings; Handbuch compiler section;
`GEOM["St"]` + `anzahl_st` (D4); confirm-card recipe rendering (sectioned: Leistung,
Vorgang-Kette, Formeln with LaTeX, Wiederverwendung/Neu panels, Warnungen); retirement of
`rezept_autor` (D2); the eval script + the four-recipe set; `POST /katalog/formel/vorschau` only
if the card work wants it.

**Out:** the visual Formel-Editor (§2 — post-Phase-3, Opus); time/lump-sum units (Std/d/Psch —
Vorhalte-family, own design); Gutachten ingestion; Lohn Stufe 2; calculator-graph changes;
automated eval thresholds.

## 9. Execution

Fable, interactively, on a worktree (`katalog-agent-phase3`), in this order: (1) D4 GEOM+
variable, (2) W18 + envelope + coverage check + near-dup warnings + tests, (3) Handbuch,
(4) retire rezept_autor, (5) card recipe rendering, (6) eval script, (7) run the four, iterate
prompt/tool ergonomics on the results, write up. Arthur reviews the eval report and the diff;
Arthur commits. Done means: all four recipes compile to valid drafts within the repair budget,
all four activate and calculate sanely (R2 exercising the new St geometry), and the reuse
behavior matches D3 to Arthur's eye on the confirm cards.
