# Spec delta: nlp-analysis-api

## ADDED Requirements

### Requirement: Ad-hoc text can be analyzed without a document
The analyze endpoint SHALL accept raw text as an alternative to a document reference (exactly one of the two per request). Ad-hoc text SHALL be segmented into PROSE blocks on blank lines — no layout inference and no reflow — and SHALL flow through the same sentence, POS, and entity analysis as document text, returning the same response shape.

#### Scenario: Analyzing LV Langtext
- **WHEN** `POST /nlp/analyze` is called with the concatenated Langtext and Hinweis of an LV item and no document uuid
- **THEN** the response contains sentences, POS statistics, and entities for that text, with no Docling inference triggered

#### Scenario: Exactly one source
- **WHEN** a request carries both a document uuid and ad-hoc text, or neither
- **THEN** the request is rejected with a validation error
