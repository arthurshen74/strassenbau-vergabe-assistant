# nlp-entities-tab Specification

## Purpose
Aggregated entity view for the NLP analysis feature: including entity statistics in the analysis response, and surfacing them in an Entities tab in the NLP Analysis modal that shows label frequency and per-occurrence provenance.

## Requirements

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

### Requirement: Entity occurrences can be flagged from the tab
Each occurrence row in the Entities tab SHALL offer a flag action opening a small form: flag kind (WRONG_LABEL or NOT_AN_ENTITY), expected label (for WRONG_LABEL), and a required comment; submitting creates the flag and shows the analysis result state inline.

#### Scenario: Flagging a wrong label from the tab
- **WHEN** the user flags the occurrence `Asphaltbeton AC` (LOC, no pattern id) as WRONG_LABEL expecting BAUSTOFF, with a comment
- **THEN** the flag is created carrying the occurrence's span, sentence, and provenance, and the row indicates its flagged state

#### Scenario: Already-flagged occurrence indicated
- **WHEN** an occurrence has an existing open flag in the current session's view
- **THEN** the row shows a flagged indicator instead of offering a duplicate flag action
