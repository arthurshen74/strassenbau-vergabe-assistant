# Katalog Agent Phase 2 Plan — Mutations

The binding spec for Phase 2 of `KATALOG_AGENT_PLAN.md`: the catalog chat agent gains **write
tools**. Every write is a draft (`entwurf`) produced through the existing bundle machinery,
confirmed by a human via a UI card, activated through the existing endpoint, auto-reloaded into
the engine. Adds the global catalog version (`katalog_stand`). Phase 1 (T1–T33 reads) is merged
and unchanged; Phase 3 (recipe compiler) stays out of scope.

**§5's W-tool list and §4's coverage matrix are the review artifacts — cross-check them before
implementation, like Phase 1's §3.**

---

## 1. Decisions

- **D1 — The agent proposes; only the human commits.** A write tool NEVER changes the active
  catalog: it validates, saves an `entwurf` bundle, and returns a draft summary. Activation
  happens exclusively through the UI confirm card → `POST /katalog/bundle/{uuid}/aktivieren`
  (existing endpoint). This is the HITL boundary, enforced structurally (§8), not by prompt.
- **D2 — The agent MAY discard.** `entwurf_verwerfen` (W17) is a permitted tool: discarding
  removes only a proposal, never touches the active catalog, and stays auditable (row archived).
  One rule to remember: *activate = human-only; everything below that = agent-allowed.*
- **D3 — "Ändern" = supersede by delta.** `aendere_*` tools take the natural key plus only the
  fields to change; the tool loads the active payload server-side, applies the delta, and saves
  the next version as a draft. The result carries a server-computed `diff` (`[{feld, alt, neu}]`)
  so the card shows exactly what changes — the LLM never retypes (and never hallucinates) the
  untouched fields.
- **D4 — `katalog_stand.version` bumps on ACTIVATION only.** The version is "the effective
  catalog's version": the number stamped onto calculations for provenance and compared for
  reloads. Draft saves and discards do NOT bump it (they change proposals, not what calculations
  use); they DO update `aktualisiert_am`/`benutzer` (the "last touched" audit display). →
  Open question §12.1 if you want every-write bumping instead.
- **D5 — Prices get a lifecycle `status`, not versions.** `katalog_lieferanten_preise` gains
  `status` (`entwurf|aktiv|archiviert`) + `bundle_uuid` + `benutzer`. Price VALUES stay immutable
  and unversioned (a correction is a new row); the status column only lets a price ride the
  draft→confirm flow like everything else. On activation of a price whose validity overlaps an
  open-ended active predecessor for the same (lieferant, baustoff), the predecessor's
  `gueltig_bis` is closed to the day before the new `gueltig_ab` — the same close-out-never-mutate
  SCD-2 move as `project_context_values`. Requires `sql/11` (ALTER; create_all cannot add columns).
- **D6 — `KatalogBundle` grows `lieferanten` and `preise`.** Discovered gap: the bundle today
  carries neither, so W5–W7 would have no write path. New fields + validation rules (§4).
  (The class was renamed `RezeptBundle` → `KatalogBundle` on this branch, 2026-07-03 — it is the
  general catalog change-set, and a recipe is just its most complex kind. No compat alias.)
- **D7 — No parked invalid drafts.** If a formula needs a DSL function that does not exist, the
  draft is NOT saved (validation would have to be weakened to persist it). The agent relays the
  enriched Rule-1 error (§7) and formulates the engineering request conversationally. The
  "draft waits in entwurf until the function ships" idea from the sketch is dropped. → §12.2.
- **D8 — Write boundary is structural.** Tools are built against a narrow facade
  (`KatalogEntwurfDienst`: `pruefen`, `entwurf_speichern`, `bundle_verwerfen` — NOT
  `bundle_aktivieren`), and the Phase-1 import-graph test becomes: the agent/tool modules never
  reference activation (§8).

## 2. `katalog_stand` — the global catalog version

New table (plain `create_all`; new tables need no SQL migration):

| Column | Type | Meaning |
|---|---|---|
| `id` | Integer PK, always `1` | singleton row |
| `version` | Integer, not null | monotonic; bumps on every bundle ACTIVATION (D4) |
| `aktualisiert_am` | timestamptz | last catalog write of ANY kind (draft/activate/discard/seed) |
| `benutzer` | Text | who performed that write |

- **Bump/touch implementation:** one repository method
  `stand_beruehren(benutzer, aktivierung: bool)` executing
  `INSERT … ON CONFLICT (id) DO UPDATE SET version = katalog_stand.version + (1 if aktivierung),
  aktualisiert_am = clock_timestamp(), benutzer = …` — called inside the SAME UoW as the write,
  from `KatalogService.entwurf_speichern` (touch), `bundle_aktivieren` (bump), `bundle_verwerfen`
  (touch). Seed inserts `version = 1, benutzer = "seed"`.
- **T1 switch:** `katalog_uebersicht` reads the row (fallback to the max-timestamp derivation
  only when the row is absent, i.e. an unseeded DB).
- **Provenance hook (cheap, this phase):** `lade_katalog` returns `stand` in its summary;
  `POST /katalog/neu-laden` therefore reports it. Stamping EKT results/ground truth with the
  version is a calculator-side change and stays OUT of this phase (noted for later).

## 3. Validation additions (extends the six store rules)

- **R7** — a bundle `preis` references an existing/bundle Lieferant AND Baustoff (by code).
- **R8** — `gueltig_ab <= gueltig_bis` when both set; `preis_eur_pro_t > 0`.
- **R9** — per-intent field whitelists: an `aendere_*` delta may only touch the entity's
  registry payload columns (unknown field = error naming the valid ones).
- **Rule-1 split (§7)** — unknown *function* vs unknown *variable* get distinct messages.

## 4. Coverage matrix (the cross-check)

Operation × entity; each cell names the W-tool or the deliberate boundary.

| Entity | neu | ändern | Notes |
|---|---|---|---|
| Baustoff | W1 | W2 | |
| Maschine | W3 | W4 | incl. Geräteklasse move, Profile |
| Lieferant | W5 | W6 | |
| Preis | W7 | — (immutable; correction = W7) | close-out on activation (D5) |
| Formel | W8 | W9 | FORMEL-variable auto-derived (existing service behavior) |
| Stammdaten-Variable | W10 | W11 (Wert) | KONSTANTE cascade |
| Kontext-Variable | W12 | — (Phase 3 if needed) | cascade assembled server-side |
| Ausführungsart (Geräteklasse) | W13 | — | rename later if needed |
| Betriebskategorie | W14 | — | |
| Betriebsart | W15 | — | |
| Leistung→BV-Mapping | W16 | (W16 is the change) | full ordered list supersede |
| Leistung / Bauverfahren / Vorgang | **Phase 3** | **Phase 3** | recipe assembly = compiler territory |
| Globale Variable | **out** | **out** | governed set; changes are engineering for now |
| Entwurf | — | W17 verwerfen | activation: human-only (D1) |

## 5. The write tools (W1–W17)

Conventions: every tool returns the **draft envelope** —
`{bundle_uuid, aktion: "neu"|"aenderung", entitaet, schluessel, bericht: {fehler, aktualisierungen},
diff?, entwurf}` — as `content_and_artifact` (JSON for the LLM, artifact for the card, §6). On
validation failure nothing is persisted and `fehler` explains why (the agent relays and may retry
with corrected input). `benutzer` = `DEFAULT_AUTOR` until auth lands.

### Baustoffe / Lieferanten / Preise

- **W1 `neuer_baustoff(code, name, rohdichte_t_pro_m3, verdichtungsfaktor?, kategorie?,
  koernung?, einheit?, basispreis_eur_pro_t?, basispreis_eur?)`**
  *„Leg den Baustoff AC 16 B S an, Rohdichte 2,4, Kategorie Asphaltmischgut."*
- **W2 `aendere_baustoff(code, aenderungen)`** — delta supersede + diff (D3).
  *„Setz beim FSS 0/32 den Basispreis auf 16,20 €/t."*
- **W3 `neue_maschine(code, hersteller, modell, ausfuehrungsart_code, eigenschaften?,
  leistungsprofile?)`** — `eigenschaften: {key: {wert, einheit?}}`,
  `leistungsprofile: [{betriebsart_code, leistung, einheit}]`. Validates the Geräteklasse and
  every Betriebsart (store Rule 4).
  *„Neue Kaltfräse: Wirtgen W 210 Fi, 340 €/h, Regelfräsen 950 m²/h."*
- **W4 `aendere_maschine(code, aenderungen)`** — scalar fields delta; `eigenschaften` merge by
  key; `leistungsprofile` replaced as a whole list when provided. A Geräteklasse move is
  `aenderungen: {ausfuehrungsart_code: …}` — one superseding version, full history retained.
  *„Verschieb die BOMAG BM 1200 in die Geräteklasse AA_KALTFRAESE."*
- **W5 `neuer_lieferant(code, name, standort, breitengrad?, laengengrad?)`**
- **W6 `aendere_lieferant(code, aenderungen)`**
- **W7 `neuer_preis(lieferant_code, baustoff_code, preis_eur_pro_t, gueltig_ab?, gueltig_bis?)`**
  — draft price row (D5); `gueltig_ab` defaults to today. The envelope warns when activation
  will close an open-ended predecessor (shows it).
  *„Harzland Schotter liefert FSS 0/32 ab 1.8. für 15,90."*

### Formeln & Variablen

- **W8 `neue_formel(name, ausdruck, einheit?)`** — full store validation (Rules 1/2/5 + §7);
  the derived FORMEL-gruppe variable rides the same bundle (existing service behavior). Envelope
  includes the LaTeX rendering + legend so the card shows real math.
  *„Neue Formel: Bankettfläche = Länge mal 1,5 m Breite je Seite mal 2."*
- **W9 `aendere_formel(name, ausdruck?, einheit?)`** — supersede; diff shows old/new `ausdruck`
  AND both LaTeX renderings.
- **W10 `neue_stammdaten_variable(name, bezeichnung, wert, einheit?, beschreibung?)`** —
  a KONSTANTE-cascade Stammdaten variable (a rate).
  *„Leg den Lohngruppen-Satz lohn_lg4_eur mit 24,80 €/h an."*
- **W11 `aendere_stammdaten_wert(name, wert)`** — THE rate-change one-liner: supersedes the
  variable with the same cascade and a new KONSTANTE. Envelope includes the T30 where-used
  summary (via `_vorgang_rollen`) so the reviewer sees the blast radius on the card.
  *„Diesel kostet jetzt 1,89."*
- **W12 `neue_kontext_variable(name, bezeichnung, einheit?, datentyp?, beschreibung?,
  llm_hinweis?, default_wert?)`** — cascade assembled server-side, mirroring the fixture
  helpers: LANGTEXT+RAG steps built from `llm_hinweis`, then HITL; `default_wert` appends a
  KONSTANTE fallback (like `mit_default`).

### Taxonomien & Mapping

- **W13 `neue_ausfuehrungsart(code, name, geraetebezug?)`** — a new Geräteklasse.
- **W14 `neue_betriebskategorie(code, bezeichnung, beschreibung?)`**
- **W15 `neue_betriebsart(code, bezeichnung, kategorie_code, einheit?, beschreibung?)`** —
  validates the Kategorie.
- **W16 `bauverfahren_zu_leistung(leistung_code, bauverfahren_codes)`** — supersedes the
  mapping row with the full ordered list (first = default; store Rule 4 validates every code;
  Rule 6 flags it as an update). The envelope shows old vs new order.
  *„Für die FSS soll künftig auch BV_FSS_FERTIGER wählbar sein, Grader bleibt Standard."*

### Lifecycle

- **W17 `entwurf_verwerfen(bundle_uuid)`** — archive a draft bundle (D2). Errors if the bundle
  has no open drafts.

## 6. Confirm card (UI)

- **New endpoint** `GET /katalog/bundle/{bundle_uuid}` → `{zustand: "offen"|"aktiviert"|
  "geschlossen", zeilen: [envelope rows]}`. Zustand rule: any `entwurf` row → `offen`; else any
  `aktiv` row → `aktiviert`; else `geschlossen` (discarded or later superseded — the card labels
  it „nicht mehr offen", no further distinction).
- **`KatalogEntwurfCard`** renders from the write tool's persisted `function_call_output`
  message (a tool-name registry maps all W-tools to the card): entity, action, the summary/diff
  (LaTeX via the existing KaTeX pipeline for W8/W9), supersede warnings from `bericht`, and the
  where-used blast radius (W11). Buttons: **Aktivieren** → `POST …/aktivieren`, **Verwerfen** →
  `POST …/verwerfen`; afterwards the card re-queries the bundle state and shows a state banner.
  On page reload the card re-queries `GET /katalog/bundle/{uuid}` first, so a card whose draft
  was long since activated or discarded renders truthfully instead of offering dead buttons.
- Hand-written component (~200 lines), consistent with the no-generic-framework decision.

## 7. Formula authoring rules

- **Vocabulary-first:** the Handbuch gains the authoring section — express the math with
  operators/ternary/whitelist (`zeige_dsl_funktionen`); *never invent a function*.
- **Rule-1 split:** the bundle validator separates AST `Call`-target names from value names.
  Unknown function → `unbekannte Funktion 'interpoliere' — keine DSL-Funktion. Verfügbar: abs,
  ceil, floor, max, min, round. Mit vorhandenem Vokabular ausdrücken oder als Entwicklerauftrag
  formulieren.` Unknown variable keeps the existing message.
- **Escalation (D7):** on unknown-function failure the agent does NOT persist anything; it
  explains the gap and drafts the engineering request in chat ({name, zweck, beispiel_aufruf})
  for the user to carry to the team. Extending `_FUNKTIONEN` remains a code change (invariant).

## 8. Write-boundary architecture

- **`KatalogEntwurfDienst`** (new, `shared/services/katalog/entwurf_dienst.py`): thin facade
  over `KatalogService` exposing `pruefen`, `entwurf_speichern`, `bundle_verwerfen` — and NOT
  `bundle_aktivieren`. All W-tools are built against it. Activation stays reachable only from
  the API route (human request).
- **Import-graph test updated:** Phase 1's "imports no write surface" becomes "the agent/tool
  modules never reference `bundle_aktivieren`" (they now legitimately import the facade).
- **Handbuch rewrite:** „ausschließlich lesend" is no longer true. New wording: the agent can
  *propose* catalog changes as drafts which the user confirms on the card; it can never activate;
  it should show the draft envelope's summary and point at the card. Werkzeug-Grammatik gains
  `neue_…`/`aendere_…`/`entwurf_verwerfen`.
- Tool count grows to ~50 (33 read + 17 write); fine for current models — the Handbuch's naming
  grammar is what keeps selection reliable.

## 9. Non-goals

- No recipe assembly (`neuer_vorgang`, `neues_bauverfahren`, `neue_leistung`) — Phase 3.
- No Globale-Variablen editing (governed set; engineering change for now).
- No Lohngruppen ENTITY (roadmap Stufe 2); note W10/W11 already enable Lohn Stufe 1 (Lohngruppen
  rates + Mittellohn formula as pure data).
- No agent-side activation under any phrasing; no auth; no bulk imports (CSV price lists); no
  parked invalid drafts (D7); no `katalog_stand` stamping into EKT results (calculator-side,
  later); no MCP.

## 10. Acceptance criteria

1. Per-tool tests W1–W17 (draft row(s) created with correct version/status/bundle_uuid; delta
   supersede preserves untouched fields; diff correct; validation failure persists nothing).
2. `katalog_stand` matrix test: seed → version 1; draft save → version unchanged,
   `aktualisiert_am` moves; activate → version +1; discard → version unchanged. T1 shows the row.
3. Price close-out test: activate an overlapping open-ended price → predecessor's `gueltig_bis`
   closed to `gueltig_ab − 1 Tag`; `preis_fuer` resolves the new price from the Stichtag on;
   history intact (T24 `mit_historie`).
4. R7–R9 + Rule-1-split unit tests (one failing fixture each; the unknown-function message names
   the whitelist).
5. End-to-end integration: W11 rate change → card data → activate via endpoint → provider
   reload → `kalkuliere` uses the new rate; discard path leaves the engine untouched.
6. Boundary test: agent/tool modules do not reference `bundle_aktivieren` (§8).
7. `sql/11` applied to the dev DB; migrated DB and fresh `create_all` DB agree on the preise
   schema. Full suite green; `gen:types` clean; UI build green.

## 11. Execution order

0. Phase 1 branch merged first (including the `_vorgang_rollen` fixes — W11 uses it).
1. `katalog_stand`: table + repo `stand_beruehren` + service hook points + seed + T1 switch (§2).
2. `sql/11` + preise status columns + provider/seed/T21/T24 filter on `aktiv` (§ D5) +
   `KatalogBundle` extension + R7–R9 (§3, §4-Preis rows).
3. Rule-1 split + Handbuch authoring section (§7).
4. `KatalogEntwurfDienst` + boundary test update (§8).
5. W-tools batch A — W8–W12 (Formeln/Variablen: the demo-relevant rate flow) + tests.
6. W-tools batch B — W1–W7, W13–W17 + tests.
7. `GET /katalog/bundle/{uuid}` + `KatalogEntwurfCard` + Handbuch rewrite + `gen:types` (§6, §8).
8. End-to-end integration (§10.5) + full-suite/build gates.

Steps 1–4 are backend-only and independently landable; 5–7 stack on them.

## 12. Open questions (answer during review)

1. **D4 bump semantics:** `version` on activation only (recommended — it's the provenance/reload
   number), with `aktualisiert_am` tracking every write. OK, or must every write bump `version`?
2. **D7:** dropping the "parked draft awaiting a DSL function" idea — conversational escalation
   only. OK?
3. **W-list completeness (§4/§5):** anything your Kalkulator changes weekly that has no W-tool?
   (Candidates deliberately excluded: Leistung/BV/Vorgang — Phase 3; Globale — governed.)
4. **W7/D5 price close-out:** auto-closing the open-ended predecessor on activation — right
   semantics, or should overlapping prices be a validation ERROR instead (forcing explicit
   `gueltig_bis` first)?
