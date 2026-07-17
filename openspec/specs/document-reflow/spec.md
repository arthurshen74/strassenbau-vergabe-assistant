# document-reflow Specification

## Purpose
Converts a document's stored `source_lines` into classified, ordered, dehyphenated content blocks (prose, heading, list, table, furniture) with line-level provenance, so downstream NLP analysis operates on clean text instead of raw layout lines.

## Requirements

### Requirement: Layout regions are inferred once per document and cached
The system SHALL infer layout regions (label, page, bbox, confidence) for a PROSE_DOCUMENT by rendering its pages from the stored raw PDF and running the Docling layout model, and SHALL persist the result keyed by document and layout-model version so inference runs at most once per document per model version.

#### Scenario: First analysis of a document
- **WHEN** a reflow is requested for a document with no cached layout regions
- **THEN** pages are rendered from MinIO, the layout model runs, and regions are stored in `document_layout_regions` before reflow proceeds

#### Scenario: Subsequent analysis
- **WHEN** a reflow is requested for a document with cached regions for the current model version
- **THEN** no page rendering or model inference occurs

### Requirement: Furniture is the union of repetition heuristic and model labels
The system SHALL flag a source line as furniture when EITHER its digit-run-normalized text plus y-position bucket repeats on at least half the document's pages (minimum 3) OR its bbox center falls inside a layout region labeled page-header or page-footer. Furniture lines SHALL be excluded from reflowed text and analysis but retained with their classification for display.

#### Scenario: Repeated letterhead the model labels inconsistently
- **WHEN** a 6-line letterhead repeats on every page and the model labels it page_header on some pages only
- **THEN** every occurrence is flagged as furniture via the repetition heuristic

#### Scenario: Roman-numeral page numbers invisible to the heuristic
- **WHEN** front-matter lines like `Seite I`, `Seite II` appear once each but fall inside model page-header/page-footer regions
- **THEN** they are flagged as furniture via the model labels

### Requirement: Lines are grouped into typed blocks in reading order
The system SHALL assign each non-furniture source line to a block typed as one of PROSE, HEADING, LIST_ITEM, TABLE, CAPTION, or FOOTNOTE, derived from the layout region containing the line's bbox center, and SHALL order blocks by document reading order. Lines covered by no region SHALL default to PROSE blocks segmented by vertical-gap heuristics.

#### Scenario: Table fragments isolated
- **WHEN** a document contains a table whose cells extract as fragment lines
- **THEN** those lines form a TABLE block and do not join any prose block

#### Scenario: Model gap fallback
- **WHEN** a content line falls outside every detected region
- **THEN** it is assigned to a PROSE block and never silently dropped

### Requirement: Text within a block is reflowed with German dehyphenation
The system SHALL join a block's lines into flowing text: a line ending in `-` joins the next line dropping the hyphen when the next line starts lowercase, and keeping the hyphen when it starts uppercase; otherwise lines join with a single space. Paragraph breaks within a block SHALL be inserted where the vertical gap exceeds 0.8 × the document's median line pitch. A block ending without terminal punctuation (or with a hyphen) SHALL merge with the next page's first block of the same type. (No lowercase test on the continuation: German capitalizes nouns, so mid-sentence continuations regularly start uppercase.)

#### Scenario: Justification hyphen dropped
- **WHEN** a line ends `gekom-` and the next line starts `menen Bindemittel`
- **THEN** the reflowed text contains `gekommenen Bindemittel`

#### Scenario: Compound hyphen kept
- **WHEN** a line ends `SRT-` and the next line starts `Pendel`
- **THEN** the reflowed text contains `SRT-Pendel`

#### Scenario: Sentence spanning a page break
- **WHEN** a prose block ends mid-sentence (no terminal punctuation) at the bottom of page 8 and page 9 starts with its continuation (e.g. the capitalized noun "Angaben")
- **THEN** the two blocks merge into one

### Requirement: Every block carries provenance to source lines
Each reflowed block SHALL record the ordered `line_id`s it was built from, so any downstream unit (sentence, token, entity) can resolve back to page and bbox of the original PDF.

#### Scenario: Sentence traced to the page
- **WHEN** a consumer asks for the origin of a sentence in a reflowed block
- **THEN** the block yields `line_id`s resolvable to (page, bbox) via `source_lines`
