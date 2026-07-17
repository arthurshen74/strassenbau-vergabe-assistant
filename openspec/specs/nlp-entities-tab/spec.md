# nlp-entities-tab Specification

## Purpose
Aggregated entity view for the NLP analysis feature: including entity statistics and a full-text entity render in the analysis response, and surfacing them in an Entities tab in the NLP Analysis modal that shows the highlighted text above label frequency and per-occurrence provenance.

## Requirements

### Requirement: Analysis responses include an aggregated entity view
The `/nlp/analyze` response SHALL include, alongside sentences and POS statistics, entity statistics: for each label found, its occurrence count and the list of occurrences (text, sentence reference, pattern id if rule-derived). The response SHALL additionally include `ent_html`: the displacy `style=ent` HTML rendered over the full analyzed text (the included blocks), produced in the same analysis pass from the same Docs as the entity statistics, so the highlight view and the breakdown can never disagree on ruler state or block filter. `ent_html` SHALL NOT be cached server-side.

#### Scenario: Entities computed alongside sentences and POS
- **WHEN** an analysis request completes
- **THEN** the response's `entities` field lists every label found across the included blocks, sorted by descending count

#### Scenario: Full-text render matches the breakdown
- **WHEN** an analysis response reports an occurrence of `AC 11 D S` under BAUSTOFF
- **THEN** the response's `ent_html` contains that same span highlighted with the BAUSTOFF label

### Requirement: The Entities tab shows the full-text entity render above the breakdown
The Entities tab SHALL render the response's `ent_html` above the label/occurrence breakdown, in a container with small typography (Tailwind `text-sm`), a maximum height of `25vh`, and a vertical scrollbar when the content overflows. When the analysis found no entities, the pane SHALL be omitted and the existing empty state shown.

#### Scenario: Render pane on top
- **WHEN** the user opens the Entities tab for an analyzed Baubeschreibung
- **THEN** the displacy entity highlights for the whole included text appear above the label frequency list, capped at 25vh with vertical scrolling

#### Scenario: Overflowing document
- **WHEN** the analyzed text's ent render is taller than 25vh
- **THEN** the pane scrolls vertically within its cap instead of pushing the breakdown off-screen

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
