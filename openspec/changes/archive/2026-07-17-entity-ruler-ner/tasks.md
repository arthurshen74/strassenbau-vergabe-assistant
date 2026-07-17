# Tasks: Entity Ruler NER

## 1. Foundation

- [x] 1.1 `server/shared/db/tables/entity_rules.py`: table (entity_rule_uuid, label, pattern JSONB, pattern_id nullable, enabled, created_at, updated_at), index on label; wire into `shared/db/tables/__init__.py` + `unit_of_work.py`
- [x] 1.2 `server/shared/models/entity_rule.py` (domain: `EntityRule`, `NewEntityRule`, `EntityRuleUpdate`) and `entity_rule_schema.py` (API schemas)
- [x] 1.3 `server/shared/repositories/entity_rules.py`: list, list_enabled, get, add, update (partial via `**changes`), delete
- [x] 1.4 Bootstrap the new table (`scripts/bootstrap_tables.py` path); confirm it appears via `\d entity_rules`

## 2. Validation and compilation

- [x] 2.1 `server/shared/services/nlp/entity_ruler.py`: `compile_pattern_dicts(rules)` (pure function → spaCy pattern dicts); `validate_pattern(label, pattern)` using a scratch `spacy.blank("de")` + `entity_ruler`, raising with spaCy's message on failure
- [x] 2.2 Unit tests: valid pattern passes, invalid token attribute rejected with a clear message, string and token-list pattern shapes both accepted

## 3. Pipeline wiring

- [x] 3.1 In `entity_ruler.py`: module-level dirty flag + lock; `mark_dirty()`; `async def ensure_ruler_current(nlp, engine)` — no-op when clean, otherwise fetches enabled rules, removes/re-adds the `entity_ruler` pipe (`overwrite_ents=True`), recompiles, clears dirty
- [x] 3.2 Call `ensure_ruler_current` at the top of `NlpService.analyze()` and `RenderService.render()` before the sync analysis/render calls
- [x] 3.3 Extend `analysis.py::analyze_blocks` to collect `doc.ents` per sentence (via char-range containment), building `EntityOccurrence`/`EntityLabelStats`/`EntityStats`; return alongside sentences and POS
- [x] 3.4 Extend `nlp.py`/`nlp_schema.py` models: `EntityOccurrence`, `EntityLabelStats`, `EntityStats`, `AnalyzeResponse.entities`
- [x] 3.5 Unit tests: ruler overrides a stock mispredict end-to-end on a real sentence; disabled rule excluded from compiled patterns; dirty flag skips DB read when clean; rule-derived occurrence carries pattern_id, stock-model occurrence doesn't

## 4. Seed script

- [x] 4.1 `server/scripts/seed_entity_rules.py`: idempotent upsert (dedupe key: hash of label+pattern_id+pattern) importing `entity_rules.json`
- [x] 4.2 Run it against the dev DB; verify row count matches the 240 authored rules

## 5. API

- [x] 5.1 `server/api/routes/entity_rules.py`: `GET /entity-rules`, `GET /entity-rules/labels`, `POST /entity-rules`, `PATCH /entity-rules/{uuid}`, `DELETE /entity-rules/{uuid}` — validate via `entity_ruler.validate_pattern` on write, call `mark_dirty()` after a successful commit
- [x] 5.2 Integration tests: create/update/delete roundtrip, invalid-pattern 422, labels endpoint reflects current distinct set
- [x] 5.3 Regenerate `ui/src/types/generated.ts`

## 6. Entity Rules admin UI

- [x] 6.1 `ui/src/api/entityRules.ts`: query-key factory + hooks (list, labels, create, update, delete)
- [x] 6.2 Add `'entity_rules'` to `MainWindowKind`; sidebar Command "View Entity Rules"; case in `MainWindow.tsx`
- [x] 6.3 `ui/src/views/main/EntityRulesView.tsx`: table (label, pattern preview, pattern_id, enabled toggle, edit/delete actions), "Add Rule" button
- [x] 6.4 `EntityRuleEditDialog.tsx`: label input with autocomplete from `/entity-rules/labels`, pattern_id input, enabled switch, raw JSON textarea for pattern with client-side `JSON.parse` check and inline server-error display

## 7. Entities tab

- [x] 7.1 `ui/src/views/nlp/EntitiesTab.tsx`: label list sorted by count, click-through occurrence list (text, sentence, pattern_id or "model guess" badge)
- [x] 7.2 Wire as the modal's fourth tab in `NlpAnalysisDialog.tsx`

## 8. Verification & docs

- [x] 8.1 Browser pass: edit a rule in the admin page, confirm the Entities tab and the Sentences-tab `ent` render both reflect the change without a restart
- [x] 8.2 Update `AI_ARCHITECTURE.md` (extend the reflow/NLP section with the ruler pipeline and flowchart)
