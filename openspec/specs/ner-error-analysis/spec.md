# ner-error-analysis Specification

## Purpose
LLM-driven error analysis of NER flags: a structured, taxonomy-constrained diagnosis per flag, driven by a versioned PromptLibrary prompt, resilient to LLM failure, with full provenance recorded on each analysis.

## Requirements

### Requirement: Each flag receives a structured LLM error analysis
Creating a flag SHALL trigger one LLM call whose prompt contains: the analyzed text, the extracted entities with labels and pattern provenance (pattern id for rule hits, an explicit statistical-model marker otherwise), the flag kind, flagged span, and user comment, the spaCy model name and version, and the full current enabled entity-rule set as JSON. The response SHALL be structured output containing a failure category from the closed taxonomy (REGISTER_MISMATCH, MISSING_RULE, RULE_ERROR, TOKENIZATION, MODEL_LIMITATION, AMBIGUITY, OTHER), a prose analysis, and an optional suggested entity rule.

#### Scenario: Analysis persisted with the flag
- **WHEN** a flag is created and the LLM call succeeds
- **THEN** the flag row holds the assigned category, the prose analysis, and the suggestion (when given), and the API returns the completed record

#### Scenario: Category is constrained to the taxonomy
- **WHEN** the LLM responds
- **THEN** the category is validated against the closed enum via the structured-output schema — a response outside it is a rejected/retried call, never a stored free-text category

### Requirement: The analysis prompt is a versioned PromptLibrary entry
The prompt SHALL be a seeded prompt of a new `PromptType` (`ner_fehleranalyse`), loaded via the PromptLibrary's latest-version lookup at call time, so edits in the Prompts UI take effect on the next flag without a deploy.

#### Scenario: Editing the prompt changes the next analysis
- **WHEN** the user edits the `ner_fehleranalyse` prompt in the Prompts UI and then creates a new flag
- **THEN** the new analysis uses the edited prompt version, and the flag records which prompt version was used

### Requirement: Analysis failure does not lose the flag
If the LLM call fails, the flag SHALL persist with an empty analysis, and the API SHALL support re-triggering analysis for such a flag.

#### Scenario: Retry after failure
- **WHEN** a flag's initial analysis failed and the user triggers re-analysis
- **THEN** a fresh LLM call runs with the current prompt version and the result is stored on the same flag

### Requirement: Every analysis records its provenance
A completed analysis SHALL record the LLM model id, the prompt version, the spaCy model name/version, and the analysis timestamp on the flag.

#### Scenario: Vintage visible on old flags
- **WHEN** the ruleset or models have changed since a flag was analyzed
- **THEN** the flag's detail still shows exactly which model, prompt version, and spaCy version produced its analysis
