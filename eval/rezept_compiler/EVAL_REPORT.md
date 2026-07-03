# Rezept-Compiler Eval — Phase 3 (KATALOG_AGENT_PHASE3_PLAN.md §7)

Date: 2026-07-03 · Model: `openai/gpt-5.4` (settings.katalog_chat_model) via OpenRouter ·
Agent: the production `katalog_chat` agent (T1–T33 + W1–W17 + W18), driven programmatically by
`server/scripts/eval_rezept_compiler.py` (no SSE). Repair budget: 3 repairs (4 W18 attempts).

**Authoritative run: [`bericht_20260703_153912.md`](bericht_20260703_153912.md)** — full
per-recipe detail (justification tables, warnings, formulas, calculation breakdowns, tool
traces, agent answers). The four draft bundles of this run are **left open in the dev DB** for
confirm-card review (uuids in the report). Earlier `bericht_*.md` files are the iteration
history and can be deleted.

## Final results

| Rezept | valid draft | repairs (budget 3) | expected reuse hits | EP | hint band | run time |
|---|---|---|---|---|---|---|
| R1 Bordstein aufnehmen (m) | yes | 0 | 6/6 | 10.70 €/m | 10–80 | 43s |
| R2 Schieberkappe auf Höhe setzen (St) | yes | 0 | 4/4 | 26.00 €/St | 20–120 | 26s |
| R3 Fräs-Verguss Risse (m) | yes | 1 | 3/3 | 5.07 €/m | 1.5–15 | 52s |
| R4 Thermocontainer Schadstellen (t) | yes | 0 | 5/5 | 235.73 €/t | 100–500 | 52s |

§9 done criteria: **all four compile to valid drafts within the repair budget; all four activate
and calculate sanely in a rolled-back transaction (menge from the real LV row); R2 exercises the
new `St` geometry (`anzahl_st`)**. Hint bands are my rough plausibility ranges, not thresholds —
the EPs are for your judgment. Reuse behavior (D3) is measured by the justification envelope:
every expected-reuse code from the plan's notes appears in `wiederverwendung` in the final run.

Measurement notes:
- (c) activation happens INSIDE a transaction that is rolled back afterwards; the running
  engine's dicts are snapshot/restored (`zustand_sichern`), so dev DB and engine stay untouched
  (the drafts themselves stay drafts).
- HITL-only kontext variables a recipe legitimately reuses (`fraesgut_klasse`,
  `materialpreis_eur_pro_t`) cannot resolve in the deterministic calc; the harness simulates the
  Kalkulator's Gate-B answer from a small table (`GATE_B_ANTWORTEN`) and reports what it
  supplied ("Gate-B-Simulation" line). In production these are Gate-B questions — by design.
- Justification coverage (d) is enforced mechanically by W18 itself: a valid save implies full
  coverage.

## What the iterations changed (prompt/tool ergonomics)

Six runs total (1 smoke + 5 full). Findings and the fixes they produced, in order:

1. **Multi-word `filter_text` finds nothing** (substring test, not tokenized): the agent
   searched `liste_ausfuehrungsarten(filter_text='hand klein geraet manuell')`, got nothing, and
   minted `AA_HANDGERAET` although `AA_KOLONNE` exists. → Handbuch: taxonomies are small — list
   them UNFILTERED before minting; `filter_text` is a substring test. Afterwards every run reused
   the right Geräteklassen (R4 reused five of them).
2. **Constant rates minted as Formeln** (`kappen_pro_h = 4`): works, but rates should stay
   maintainable via `aendere_stammdaten_wert`. → Handbuch: "Ansätze sind Stammdaten, keine
   konstanten Formeln."
3. **One-shot harness vs. clarifying questions**: with no follow-up turn the agent (correctly,
   per Handbuch) asked instead of compiling. → eval prompt now authorizes conservative
   assumptions ("Rückfragen kann ich nicht beantworten … speichere JETZT"). Production behavior
   is unchanged — asking is right when a Kalkulator is present.
4. **Per-recipe crew-size mints** (`thermocontainer_kolonne_mann` etc.) instead of
   `anzahl_arbeiter` — the near-duplicate warning flagged it (score 6.8) every time. → Handbuch:
   Kolonnenstärke is the kontext variable `anzahl_arbeiter`, like every existing recipe.
5. **Foreign-geometry trap** (the big one): recipes that validate but cannot calculate
   deterministically because a formula — or a REUSED m²-based chain member (`V_FRAESEN` in the
   t-billed R4) — transitively depends on a geometry variable that is never booked for the billed
   unit. → new W18 **geometry warning**: a transitive walk over active ∪ bundle formulas, seeded
   from every Vorgang in the recipe's chains (incl. reused ones); Handbuch geometry paragraph
   sharpened ("NUR von der gebuchten Größe rechnen"). In the final run the agent minted
   t-calibrated Vorgänge with explicitly geometry-aware justifications.
6. **Agent gave up after a failed repair** (reported conversationally instead of retrying). →
   Handbuch: repeat correct+call until saved; don't stop after one failure.

The repair loop itself worked exactly as designed throughout: every failure was returned as
`bericht.fehler`, and the observed repairs were coverage catches (an unjustified referenced code)
and one Rule-5 gruppe collision — each fixed in a single iteration.

## D3 judgment items for the card review

- **R4 chain granularity**: the agent minted four t-calibrated Vorgänge (ausschneiden/fräsen,
  säubern, anspritzen, verfüllen+verdichten) instead of reusing the m²-based `V_FRAESEN`/
  `V_ANSPRITZEN`/`V_REINIGEN_KEHREN`. Its justifications name the geometry reason explicitly.
  Near-duplicate warnings on the cards point at the m² counterparts — this is the calibrated
  Betriebsart/Vorgang boundary of D3 in action; your call on the cards.
- **R4 EP 235.73 €/t** decomposes into Material 360 € (5 t × 120 €/t incl. my simulated
  frei-Bau price), Lohn/Maschine dominated by the Thermocontainer step (3 men, 1.5 t/h). The
  driver assumptions (Gerätesätze) are minted Stammdaten variables — all visible and adjustable
  via W11.
- **Betonaufbruch-Entsorgungssatz (R1)** and **Vergussmasse/Rissfräse (R3)** were minted as the
  plan's expected-mints notes predicted.
- One residual geometry warning on R4's Fräs-Vorgang flags a `flaeche_m2` dependency inside a
  ternary branch that the calc never took (`fraesgut_klasse=1` → 0 € Entsorgung). The static
  warning is conservative by design; the card shows it.

## Recommendation

The compiler meets §9 as-is. Worth considering post-review (not done, out of §8 scope or
needs your call):

- The near-duplicate threshold (`DUBLETTEN_SCHWELLE = 3.5`) is calibrated on today's catalog
  scores; revisit when the catalog grows.
- `POST /katalog/formel/vorschau` (§2) was NOT needed by the card work — deferred as the plan
  allowed.
- Run-to-run variance is real (one run failed R3's save when the agent stopped repairing —
  fixed by finding 6, but sampling remains a factor). If you want tighter guarantees, a second
  seeded example in the Handbuch would be the next lever.
