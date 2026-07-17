# Tasks: NER Error Investigation

## 1. Ad-hoc text analysis

- [x] 1.1 `AnalyzeRequest`: optional `text`, `document_uuid` now optional, model validator enforcing exactly one; `NlpService.analyze` text path (blank-line split into PROSE blocks, no layout/reflow)
- [x] 1.2 Unit + integration tests: LV-style text analyzed end-to-end, both-sources and no-source rejected 422
- [x] 1.3 Modal source switch: document picker / free-text textarea / preloaded text via prop; `useNlpAnalysis` keyed by text hash for ad-hoc mode
- [x] 1.4 "NLP-Analyse" action on LV items (table row + `LVItemDetailDialog`) opening the modal with `langtext` + `hinweis`

## 2. Flag foundation

- [x] 2.1 Enums: `NerFlagKind` (WRONG_LABEL, NOT_AN_ENTITY, MISSED_ENTITY), `NerFailureCategory` (REGISTER_MISMATCH, MISSING_RULE, RULE_ERROR, TOKENIZATION, MODEL_LIMITATION, AMBIGUITY, OTHER), `NerFlagStatus` (OPEN, RESOLVED)
- [x] 2.2 `server/shared/db/tables/ner_flags.py`: uuid pk, kind, span_text, span_start/end, sentence_text, label, expected_label nullable, user_comment, source_text, entity_snapshot JSONB, lv_item_uuid/document_uuid nullable FKs (SET NULL), category nullable, category_override nullable, llm_analysis nullable, suggested_rule JSONB nullable, llm_model/prompt_version/spacy_model_version/analyzed_at nullable, status, resolved_note, timestamps; CHECK constraints from enums
- [x] 2.3 Domain models + API schemas (`NerFlag`, `NewNerFlag`, `NerFlagUpdate`, list/summary shapes with effective-category logic)
- [x] 2.4 Repository: add, get, list with kind/category/status filters, update (partial), delete, category-count aggregation (effective category, split by status); wire table + repo into `__init__`/UoW; bootstrap
- [x] 2.5 Repository integration tests incl. aggregation and override-wins counting

## 3. Prompt type (follow ADDING_A_PROMPT_TYPE.md fully)

- [x] 3.1 `PromptType.NER_FEHLERANALYSE = "ner_fehleranalyse"` in enums
- [x] 3.2 `server/scripts/seed/prompts/ner_fehleranalyse.prompt`: frontmatter (model, temperature) + template with placeholders (text, entities+provenance, flag kind/span/comment, spaCy model, entity rules JSON) and instructions to categorize against the taxonomy and optionally suggest a rule
- [x] 3.3 `sql/NN_*.sql` migration widening both `prompt_type` CHECK constraints; apply to dev DB; run prompt seed
- [x] 3.4 Update the two prompt lock tests; regenerate TS types; update the hardcoded UI prompt-type lists

## 4. Error analysis service

- [x] 4.1 `server/shared/services/nlp/error_analysis.py`: structured output model (category enum, analysis, optional suggested_rule), prompt assembly (entities with pattern_id or "statistisches Modell", enabled rules JSON from repo, spaCy model version), `get_latest(NER_FEHLERANALYSE)` load, LLMClient structured call, flag row update with provenance
- [x] 4.2 Failure handling: LLM error leaves the flag with null analysis; re-analyze path reuses the same function
- [x] 4.3 Unit tests with a stubbed LLM client: prompt contains all five context sections; category validated; failure keeps flag; provenance recorded

## 5. API

- [x] 5.1 `server/api/routes/ner_flags.py`: `POST /ner-flags` (create + synchronous analysis), `GET /ner-flags` (filters), `GET /ner-flags/summary` (category counts), `PATCH /ner-flags/{uuid}` (override, resolve/reopen with note), `POST /ner-flags/{uuid}/analyze` (retry), `DELETE /ner-flags/{uuid}`; register router
- [x] 5.2 Integration tests (stubbed LLM via dependency override): create-with-analysis roundtrip, retry after failure, summary aggregation, filters
- [x] 5.3 Regenerate `ui/src/types/generated.ts`

## 6. Flag capture UI

- [x] 6.1 `ui/src/api/nerFlags.ts`: hooks (create, list, summary, update, retry, delete) + query keys
- [x] 6.2 `FlagEntityDialog`: kind (WRONG_LABEL/NOT_AN_ENTITY), expected-label input, comment; pending/success/failed analysis state
- [x] 6.3 Entities tab: flag action per occurrence row + flagged indicator
- [x] 6.4 Sentences tab: within-sentence text selection → missed-entity flag (same dialog, MISSED_ENTITY preset); cross-sentence selection disabled with hint

## 7. NER Analysis page

- [x] 7.1 `'ner_analysis'` MainWindowKind + sidebar command + MainWindow case
- [x] 7.2 `NerAnalysisView`: summary header (per effective category, AMBIGUITY red, resolved share), filter bar, flag list
- [x] 7.3 Flag detail panel: sentence/source text, snapshot, comment, analysis prose, provenance, suggested rule as copyable JSON with Entity Rules pointer; actions (resolve with note, reopen, category override, re-analyze, delete)

## 8. Verification & docs

- [x] 8.1 Browser pass: LV item → modal → flag a wrong label and a miss → analyses persisted → dashboard counts update → resolve loop with a rule added in Entity Rules
- [x] 8.2 Update `AI_ARCHITECTURE.md` (error-investigation flow in the NLP section) and `APPLICATION_ARCHITECTURE.md` (ner_flags table, /ner-flags routes)
