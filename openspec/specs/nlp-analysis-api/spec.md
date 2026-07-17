# nlp-analysis-api Specification

## Purpose
HTTP surface for the NLP analysis feature: serves reflowed text with block metadata, runs sentence/POS analysis with block-type inclusion parameters, and generates and caches displacy renders.

## Requirements

### Requirement: Reflowed text is served with block metadata
The API SHALL return a document's reflowed content as an ordered list of blocks (type, text, page range, line_id range, furniture excluded) plus the original lines on request, so the UI can render both views and dim excluded content.

#### Scenario: Reflowed view
- **WHEN** `GET /nlp/documents/{uuid}/text` is called
- **THEN** it returns ordered typed blocks with reflowed text and provenance ranges

### Requirement: Sentence and POS analysis respects a block-type include list
The API SHALL run spaCy analysis (`de_core_news_lg`) over the reflowed blocks whose type is in the request's `include_blocks` list, defaulting to PROSE, HEADING, and LIST_ITEM. The response SHALL contain per-sentence entries (text, block reference, sentence hash) and aggregate POS statistics: counts and percentages per coarse UD tag and per fine STTS tag, with the token list retrievable per tag. FURNITURE SHALL NOT be accepted in `include_blocks`.

#### Scenario: Default analysis
- **WHEN** `POST /nlp/analyze` is called with only a document uuid
- **THEN** sentences come exclusively from PROSE, HEADING, and LIST_ITEM blocks

#### Scenario: Tables opted in
- **WHEN** `POST /nlp/analyze` includes TABLE in `include_blocks`
- **THEN** table block text is segmented and analyzed like any other included block

#### Scenario: POS drill-down
- **WHEN** the analysis response reports 312 NOUN tokens
- **THEN** the tokens (text, lemma, sentence reference) behind that count are available to the client

### Requirement: Displacy renders are served per sentence
The API SHALL render a sentence's dependency parse as displacy SVG (`style=dep`) and its entities as displacy HTML (`style=ent`). Dep SVGs SHALL be cached keyed by sha256 of spaCy model name, model version, style, and sentence text; ent HTML SHALL be generated per request from the Doc's entities (never cached, so a future entity source change shows immediately).

#### Scenario: Dep render cached
- **WHEN** the same sentence's dep render is requested twice
- **THEN** the second response is served from `nlp_render_cache` without re-parsing

#### Scenario: Model upgrade invalidates cache
- **WHEN** the spaCy model version changes
- **THEN** previously cached renders are not served for new requests

### Requirement: Ad-hoc text can be analyzed without a document
The analyze endpoint SHALL accept raw text as an alternative to a document reference (exactly one of the two per request). Ad-hoc text SHALL be segmented into PROSE blocks on blank lines — no layout inference and no reflow — and SHALL flow through the same sentence, POS, and entity analysis as document text, returning the same response shape.

#### Scenario: Analyzing LV Langtext
- **WHEN** `POST /nlp/analyze` is called with the concatenated Langtext and Hinweis of an LV item and no document uuid
- **THEN** the response contains sentences, POS statistics, and entities for that text, with no Docling inference triggered

#### Scenario: Exactly one source
- **WHEN** a request carries both a document uuid and ad-hoc text, or neither
- **THEN** the request is rejected with a validation error

### Requirement: NLP models load lazily
spaCy and Docling models SHALL NOT load at API startup; they SHALL load on first use and stay resident.

#### Scenario: API boots without models
- **WHEN** the API process starts
- **THEN** no spaCy or Docling weights are loaded until the first `/nlp/*` request needing them
