# Entity Ruler NER

## Why

Requirement 2 of the graded project (NER) needs entities associated with metadata and an aggregated overview. The stock spaCy model's PER/LOC/ORG/MISC labels are nearly blind on Baubeschreibung vocabulary (`Asphaltbeton AC` guessed as LOC; `Bauablaufplan` ignored entirely) — verified in the prior change. Arthur authored a 240-rule EntityRuler pattern set (`server/shared/services/nlp/entity_rules.json`, 14 domain labels: `BAUSTOFF`, `AUSBAUSTOFF`, `BAU_VORGAENGE`, `FGSV_REGELWERK`, `DIN_NORM`, …) covering exactly this gap. Loading it live-editable into Postgres — instead of a static file — lets the ruleset improve iteratively as false positives/negatives surface in the modal, without a redeploy.

## What Changes

- New Postgres table `entity_rules` (label, pattern JSONB, optional grouping `pattern_id`, `enabled`) — CRUD-managed, seeded once from the existing JSON file.
- New `entity_ruler` pipe added to the shared spaCy singleton (`overwrite_ents=True`, so domain rules override generic mispredictions), rebuilt lazily in-process whenever rules change.
- New dedicated **Entity Rules** admin page (MainWindow, alongside Prompts/Katalog): list, create, edit, enable/disable, delete rules; pattern edited as raw JSON, validated against spaCy on save.
- `/nlp/analyze` response gains an `entities` field: per-label counts and occurrences (text, sentence, pattern provenance) — computed in the same spaCy pass as sentences/POS, no extra parsing.
- New **Entities** tab in the NLP Analysis modal: aggregated frequency by label, occurrence list, and a visible distinction between rule-derived entities (have a `pattern_id`) and stock-model guesses (don't) — directly supporting requirement 3's "investigate wrongly predicted entities."
- The existing per-sentence `ent` render (Sentences tab) automatically reflects the ruleset once the pipeline change lands — no UI change needed there.

Out of scope: generating patterns from Katalog rows (`katalog_baustoffe`, `katalog_maschinen`, …) — this change loads Arthur's hand-authored rules only; Katalog-derived pattern generation is a natural, separately-scoped follow-up. Also out of scope: SpanRuler-based ambiguity/overlap surfacing — the authored rule set has no internal overlaps (verified), so plain `EntityRuler` conflict resolution (longest match) is sufficient.

## Capabilities

### New Capabilities

- `entity-rule-management`: the `entity_rules` table, CRUD API with spaCy-validated writes, seed script, and the admin UI page.
- `entity-ruler-pipeline`: wiring a DB-backed `EntityRuler` into the shared spaCy singleton with lazy invalidation, and extracting entity occurrences during analysis.
- `nlp-entities-tab`: the modal's aggregated Entities tab and the `AnalyzeResponse.entities` extension it consumes.

### Modified Capabilities

_None formally — the prior change (`nlp-analysis-modal`) is not yet archived, so its specs aren't canonical yet. This change extends `/nlp/analyze`'s response shape and adds a modal tab in practice (see Impact); once `nlp-analysis-modal` is archived, a future change should reconcile the specs._

## Impact

- `server/shared/db/tables/entity_rules.py`, `server/shared/repositories/entity_rules.py` — new table + repository.
- `server/shared/services/nlp/entity_ruler.py` — pattern compilation, spaCy validation, ruler pipe management, dirty-flag invalidation.
- `server/shared/services/nlp/analysis.py` — `analyze_blocks` also collects `doc.ents` per sentence.
- `server/shared/models/entity_rule.py`, `entity_rule_schema.py`, extensions to `nlp.py`/`nlp_schema.py` (`EntityOccurrence`, `EntityLabelStats`, `EntityStats`, `AnalyzeResponse.entities`).
- `server/api/routes/entity_rules.py` — new CRUD routes; `server/api/routes/nlp.py` unchanged (response shape grows, endpoint doesn't).
- `server/scripts/seed_entity_rules.py` — one-time idempotent import from the JSON fixture.
- `ui/src/store/mainWindow.ts`, `ui/src/components/mainwindow/MainWindow.tsx` — new `entity_rules` window kind.
- `ui/src/views/main/EntityRulesView.tsx` + edit dialog, `ui/src/api/entityRules.ts` — new admin page.
- `ui/src/views/nlp/EntitiesTab.tsx`, `ui/src/api/nlp.ts` — new tab, `AnalyzeResponse` type regenerated.
