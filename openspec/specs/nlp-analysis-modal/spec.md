# nlp-analysis-modal Specification

## Purpose
The three-tab UI modal for the NLP analysis feature — text view with an original-lines toggle, sentence view with per-sentence displacy renders, and a POS histogram with drill-down — including the block-type inclusion toggles.

## Requirements

### Requirement: Modal opens preloaded with exactly one source
The NLP analysis modal SHALL NOT contain a document picker, a free-text input, or a source toggle. It SHALL open only via a launch action that fixes its source: a document (from a Baubeschreibung's "NLP-Analyse" action in the Project Documents tab) or ad-hoc text (an LV item's Langtext and Hinweis from its "NLP-Analyse" action). The active source SHALL be labeled in the modal (file name, or the LV reference). The analysis tabs (Text, Sentences, POS, Entities) run over the preloaded source immediately.

#### Scenario: Opening from the Documents tab
- **WHEN** the user clicks "NLP-Analyse" on an ingested Baubeschreibung row in the Project Documents tab
- **THEN** the modal opens on that document, the Text tab shows its reflowed text, and no source controls are shown

#### Scenario: Opening from an LV item
- **WHEN** the user triggers "NLP-Analyse" on an LV position with Langtext and Hinweis
- **THEN** the modal opens with that text preloaded and analyzed, labeled with the LV reference

#### Scenario: No bare launch
- **WHEN** the user looks for a global "NLP Analysis" command (sidebar)
- **THEN** none exists — the modal is reachable only through a source's launch action

### Requirement: The Project Documents tab offers an NLP launch per analyzable document
In the Project Documents tab, each PROSE_DOCUMENT row whose ingest has produced source lines SHALL show an "NLP-Analyse" launch action alongside the existing row actions. LV_DOCUMENT rows and PROSE_DOCUMENT rows without extracted source lines SHALL NOT show the action.

#### Scenario: Analyzable row
- **WHEN** a Baubeschreibung has completed ingest
- **THEN** its row shows the "NLP-Analyse" action, and clicking it opens the modal on that document

#### Scenario: Non-analyzable rows
- **WHEN** a row is an LV_DOCUMENT, or a Baubeschreibung whose ingest has not produced source lines
- **THEN** the row shows no "NLP-Analyse" action

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

### Requirement: Text can be selected and flagged as a missed entity
Within a sentence in the Sentences tab, the user SHALL be able to select a span of text and flag it as a missed entity, choosing the expected label and entering a comment. Selections spanning multiple sentences SHALL be rejected with a hint.

#### Scenario: Flagging a miss
- **WHEN** the user selects `Bordstein` inside one sentence and submits the missed-entity flag form with label BAUSTOFF and a comment
- **THEN** a MISSED_ENTITY flag is created for that span and its sentence

#### Scenario: Cross-sentence selection rejected
- **WHEN** the user's selection crosses a sentence boundary
- **THEN** the flag affordance is disabled with a hint to select within one sentence
