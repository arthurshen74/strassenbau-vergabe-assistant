# nlp-analysis-modal Specification

## Purpose
The three-tab UI modal for the NLP analysis feature — text view with an original-lines toggle, sentence view with per-sentence displacy renders, and a POS histogram with drill-down — including the block-type inclusion toggles.

## Requirements

### Requirement: Modal opens from a document picker with three tabs
The UI SHALL provide an NLP analysis modal listing analyzable documents grouped by project; selecting one shows three tabs: Text, Sentences, and POS.

#### Scenario: Opening
- **WHEN** the user opens the NLP modal and picks a Baubeschreibung
- **THEN** the Text tab shows its reflowed text

### Requirement: Text tab shows reflowed text with an original-lines toggle
The Text tab SHALL render the reflowed blocks and provide a toggle to the original source lines view in which furniture and excluded block types are visibly dimmed and labeled with their block type.

#### Scenario: Inspecting what reflow removed
- **WHEN** the user switches the toggle to original lines
- **THEN** furniture lines (letterhead, page numbers) appear dimmed with their classification, and reflow effects (dehyphenation) can be compared against the reflowed view

### Requirement: Block-type inclusion is user-adjustable
The modal SHALL show one toggle per selectable block type (PROSE, HEADING, LIST_ITEM, TABLE, CAPTION, FOOTNOTE) with PROSE, HEADING, and LIST_ITEM on by default; changing them re-runs analysis with the corresponding `include_blocks`.

#### Scenario: Enabling tables
- **WHEN** the user enables the TABLE toggle
- **THEN** the Sentences and POS tabs refresh including table block text

### Requirement: Sentences tab renders per-sentence displacy on demand
The Sentences tab SHALL list sentences grouped by block, each with a dep button and an ent button; clicking fetches the render (SVG for dep, HTML for ent) and displays it inline inside a horizontally scrollable container. Renders SHALL be fetched only on click, never eagerly.

#### Scenario: Viewing a dependency parse
- **WHEN** the user clicks the dep button on a sentence
- **THEN** the displacy SVG appears inline under that sentence in an `overflow-x: auto` container

#### Scenario: Viewing entities
- **WHEN** the user clicks the ent button
- **THEN** the displacy entity HTML appears inline, styled within a scoped wrapper

### Requirement: POS tab shows a normalized histogram with granularity toggle and drill-down
The POS tab SHALL show percentage-normalized tag distribution as a horizontal bar chart, defaulting to coarse UD tags with a toggle to fine STTS tags; clicking a bar SHALL list the tokens (text, lemma, containing sentence) behind it.

#### Scenario: Comparing granularities
- **WHEN** the user toggles from UD to STTS
- **THEN** the chart re-renders with fine-grained tags (e.g. NN vs NE) as percentages

#### Scenario: Drill-down
- **WHEN** the user clicks the NOUN bar
- **THEN** a token list shows every noun with its lemma and sentence
