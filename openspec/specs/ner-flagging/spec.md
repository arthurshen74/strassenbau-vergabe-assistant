# ner-flagging Specification

## Purpose
Capturing NER mispredictions as persisted flags: three misprediction shapes, a self-contained snapshot of the analysis context, listing/filtering/resolving, and a user-overridable failure category.

## Requirements

### Requirement: Mispredictions can be flagged in three shapes
The system SHALL support flagging a misprediction as one of: WRONG_LABEL (an extracted entity carries the wrong label), NOT_AN_ENTITY (an extracted span should not be an entity at all), or MISSED_ENTITY (a text span that should have been extracted but was not). Every flag SHALL carry the flagged span text, its containing sentence, the label involved (the wrong one, or the expected one for misses), and a free-text user comment.

#### Scenario: Flagging a wrongly labeled entity
- **WHEN** the user flags the occurrence `Asphaltbeton AC` (labeled LOC) with kind WRONG_LABEL and a comment
- **THEN** a flag is persisted recording the span, sentence, label LOC, kind, and comment

#### Scenario: Flagging a miss from a text selection
- **WHEN** the user selects `Bordstein` inside a sentence and flags it as MISSED_ENTITY with expected label BAUSTOFF
- **THEN** a flag is persisted with kind MISSED_ENTITY and the expected label

### Requirement: Flags snapshot their analysis context
A flag SHALL store the full analyzed source text, the flag-time entity list (spans, labels, pattern ids) as structured data, and — when the analyzed text came from an LV item or document — a nullable reference to that source. A flag on ad-hoc pasted text SHALL be fully interpretable with no source reference.

#### Scenario: Ad-hoc text flag stands alone
- **WHEN** a flag is created from analysis of pasted free text
- **THEN** the flag row contains the complete text and entity snapshot, with no document or LV item reference

#### Scenario: LV-derived flag keeps its source link
- **WHEN** a flag is created from an LV item's Langtext analysis
- **THEN** the flag references that `lv_item_uuid` in addition to the snapshot

### Requirement: Flags are listable, filterable, and resolvable
The API SHALL list flags with filters for kind, failure category, and status, and SHALL support resolving a flag with a note and reopening it. Deleting a flag SHALL be possible.

#### Scenario: Resolving after a rule fix
- **WHEN** the user resolves a flag with note "added rule baustoff_bordstein"
- **THEN** the flag's status is RESOLVED with that note, and it appears under resolved in filtered lists

### Requirement: The failure category can be overridden by the user
A flag SHALL carry both the LLM-assigned failure category and an optional user override; wherever a single category is displayed or aggregated, the override SHALL win.

#### Scenario: Correcting the LLM's categorization
- **WHEN** the LLM categorized a flag as MODEL_LIMITATION and the user overrides it to REGISTER_MISMATCH
- **THEN** lists and dashboard counts attribute the flag to REGISTER_MISMATCH
