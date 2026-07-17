# Spec: nlp-entities-tab

## ADDED Requirements

### Requirement: Analysis responses include an aggregated entity view
The `/nlp/analyze` response SHALL include, alongside sentences and POS statistics, entity statistics: for each label found, its occurrence count and the list of occurrences (text, sentence reference, pattern id if rule-derived).

#### Scenario: Entities computed alongside sentences and POS
- **WHEN** an analysis request completes
- **THEN** the response's `entities` field lists every label found across the included blocks, sorted by descending count

### Requirement: The modal has an Entities tab showing frequency and provenance
The NLP Analysis modal SHALL provide a fourth tab listing entity labels by frequency; selecting a label SHALL show its occurrences with the containing sentence text and, when present, the rule that produced it.

#### Scenario: Distinguishing rule hits from model guesses
- **WHEN** the user opens the Entities tab and selects a label
- **THEN** each occurrence row shows either its originating rule (pattern id) or is visibly marked as a stock-model guess when no rule produced it

#### Scenario: Empty result is not an error
- **WHEN** the included blocks contain no entities of any label
- **THEN** the tab shows an empty state rather than an error
