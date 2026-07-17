# NER Error Investigation

## Why

Requirement 3 of the graded project: investigate wrongly predicted entities — NER accuracy degrades outside English/news domains, and the findings should explain why. Today a misprediction observed in the NLP modal (wrong label, phantom entity, or a miss like `Bordstein` → LOC) is ephemeral: nothing captures it, nothing analyzes it, nothing aggregates it. This change turns each observed error into a persisted, LLM-analyzed, categorized record — building an error corpus whose summary ("25 flags: 9 register mismatch, 7 missing rules, 4 tokenization, 3 ambiguity") *is* the requirement-3 deliverable. It also brings LV Langtext/Hinweis into the modal (all 1,405 LV items carry Langtext, 913 a Hinweis), completing the prose-vs-telegram register contrast the NER investigation needs.

## What Changes

- `/nlp/analyze` learns to analyze **ad-hoc text** (no document): LV Langtext+Hinweis, or free text pasted into the modal. Short texts skip Docling/reflow entirely — blank-line-split PROSE blocks.
- LV items table/detail gain an **"NLP-Analyse"** action opening the modal preloaded with that position's Langtext/Hinweis.
- **Flagging** in the modal: flag an entity occurrence (Entities tab) as wrongly labeled or not-an-entity, or select text in a sentence (Sentences tab) and flag it as a *missed* entity; each flag takes a prose comment describing what's wrong.
- Each flag triggers a **one-shot LLM error analysis** (existing LLM client via OpenRouter): prompt built from the analyzed text, extracted entities with their `pattern_id` provenance, the user's comment, the spaCy model identity, and the full current entity-rule set from the `entity_rules` table. The prompt is a seeded, versioned **PromptLibrary** entry (new `PromptType`, per `ADDING_A_PROMPT_TYPE.md`), editable in the Prompts UI. The LLM returns structured output: a failure category (closed enum), a prose analysis, and optionally a suggested entity-rule fix.
- New **`ner_flags` table** persisting flag + analysis + model/prompt/ruleset provenance, with an open/resolved status for closing the loop (missing rule → rule added in the Entity Rules page → flag resolved).
- New **NER Analysis** page (MainWindow, beside Prompts/Entity Rules): summary dashboard of failure-category counts (ambiguity highlighted red), filterable flag list, detail view with the full LLM analysis and rule suggestion, resolve action.

Out of scope: automatic rule creation from LLM suggestions (the suggestion is displayed; applying it goes through the Entity Rules admin page by hand), batch re-analysis of old flags after ruleset changes, and cross-document entity dynamics.

## Capabilities

### New Capabilities

- `ner-flagging`: capturing mispredictions — flag kinds (wrong label / not an entity / missed entity), span+sentence+source provenance, user comment, persistence, CRUD API.
- `ner-error-analysis`: the one-shot LLM analysis — PromptLibrary prompt, structured output (failure category enum, analysis, optional rule suggestion), stored on the flag with model/prompt-version provenance.
- `ner-analysis-dashboard`: the browse/summary UI — category-count dashboard, filterable flag list, detail + resolve.

### Modified Capabilities

- `nlp-analysis-api`: gains analyze-ad-hoc-text (document-less analysis for LV/free text).
- `nlp-analysis-modal`: gains an ad-hoc text source (LV entry + free text) and text-selection flagging in the Sentences tab.
- `nlp-entities-tab`: occurrence rows gain the flag action (wrong label / not an entity).

## Impact

- Builds on the implemented+archived `entity-ruler-ner` (78e8cf4): reads `entity_rules` for the prompt, reuses `EntityOccurrence.pattern_id` provenance, extends `EntitiesTab.tsx`.
- `server/shared/db/tables/ner_flags.py`, repository, `NerFlagKind`/`NerFailureCategory`/`NerFlagStatus` enums, Pydantic models + schemas.
- `server/shared/services/nlp/error_analysis.py` — prompt assembly + structured LLM call; `server/scripts/seed/prompts/ner_fehleranalyse.prompt` + new `PromptType` member.
- `server/shared/services/nlp/service.py`/`analysis.py` — ad-hoc text analysis path; `server/api/routes/nlp.py` + new `server/api/routes/ner_flags.py`.
- UI: `ui/src/api/nerFlags.ts`, flag affordances in `SentencesTab`/`EntitiesTab`, LV table/detail action, new `NerAnalysisView` MainWindow page + sidebar command, regenerated types.
- API gains its first LLM-calling NLP endpoint: flag creation latency includes one chat call (~20k prompt tokens with the full ruleset); logged via `prompt_execution_log`/`openrouter_usage` like every other call.
