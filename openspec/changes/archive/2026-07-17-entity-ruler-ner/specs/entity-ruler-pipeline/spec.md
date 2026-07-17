# Spec: entity-ruler-pipeline

## ADDED Requirements

### Requirement: Enabled rules are compiled into the shared spaCy pipeline
The system SHALL add an `entity_ruler` pipe to the shared spaCy singleton, configured to override overlapping entities from the stock NER component, compiled from every rule where `enabled` is true.

#### Scenario: Ruler overrides a stock mispredict
- **WHEN** a sentence contains text matching both a domain rule and the stock model's NER
- **THEN** the resulting entity carries the rule's label, not the stock model's

#### Scenario: Disabled rules excluded
- **WHEN** a rule's `enabled` field is false
- **THEN** its pattern is absent from the compiled pipeline

### Requirement: The compiled pipeline reflects the latest rules without a restart
The system SHALL invalidate its compiled ruler whenever a rule is created, updated, deleted, or toggled, and SHALL recompile from the current enabled rule set on the next analysis or render call after invalidation — never serving a stale compiled ruler once rules have changed.

#### Scenario: Edit takes effect on the next call
- **WHEN** a rule is edited and an analysis is subsequently requested for any document
- **THEN** the returned entities reflect the edited rule, with no process restart required

#### Scenario: No DB read when nothing changed
- **WHEN** no rule has changed since the ruler was last compiled
- **THEN** an analysis or render call does not re-fetch rules from the database

### Requirement: Entity occurrences are attributed to sentences during analysis
When computing sentence and POS statistics for a document, the system SHALL also collect every entity found (from the ruler or the stock model), each carrying its text, label, the id of the pattern that produced it (absent for stock-model entities), and the sentence it occurred in.

#### Scenario: Rule-derived entity carries provenance
- **WHEN** a span matches a rule with `pattern_id` "baustoff_beton"
- **THEN** the corresponding entity occurrence records "baustoff_beton" as its pattern id

#### Scenario: Stock-model entity has no rule provenance
- **WHEN** a span is tagged only by the stock NER component (no rule matched)
- **THEN** the corresponding entity occurrence has no pattern id, distinguishing it as a model guess
