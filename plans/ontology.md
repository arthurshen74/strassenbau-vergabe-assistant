# Graph Ontology

Schema definition for the case-preparation knowledge graph. Written for two readers: humans extending the schema, and AI agents reasoning over it.

## Overview

The graph represents a German labor-law case (Kündigungsschutzklage) as a network of:

- **Documents** — Schriftsätze (legal pleadings) and evidence files
- **Paragraphs** — numbered units within Schriftsätze
- **Assertions** — atomic factual claims extracted from paragraphs
- _(future)_ People, Events, Legal Elements
- _(future)_ Semantic edges across documents (support, contradiction, references)

This file is the source of truth for the schema. Update it whenever a new node label, relationship type, or property is added — both for currently-implemented elements and for planned ones.

## Conventions

- **Node labels**: `PascalCase` — e.g., `Document`, `Paragraph`, `Assertion`.
- **Relationship types**: `SCREAMING_SNAKE_CASE` — e.g., `HAS_PARAGRAPH`, `CONTAINS_ASSERTION`, `NEXT`.
- **Property names**: `snake_case` — e.g., `filing_date`, `text_de`.
- **IDs**: stable, human-readable, deterministic. Never UUIDs.
- **Dates**: stored as Neo4j `date` or `datetime` types, never strings.
- **Embeddings**: stored as native Neo4j `VECTOR<FLOAT32>(N)` where N matches the embedding model dimension.

## Current Schema

### Node: `Document`

A Schriftsatz (legal filing) or source evidence document.

**Required properties** (enforced in application code via Pydantic):

| Property        | Type   | Allowed values / notes                                                                                                     |
| --------------- | ------ | -------------------------------------------------------------------------------------------------------------------------- |
| `id`            | string | Unique. Pattern: `{document_type_lower}_{yyyy_mm_dd}` (e.g., `klageerwiderung_2026_04_09`)                                 |
| `document_type` | string | One of: `Klageschrift`, `Klageerweiterung`, `Klageerwiderung`, `Replik`, `Schriftsatz`, `Beschluss`, `Protokoll`, `Anlage` |
| `filing_date`   | date   | Date filed with the court                                                                                                  |
| `filing_party`  | string | One of: `plaintiff`, `defendant`, `court`                                                                                  |
| `aktenzeichen`  | string | Case reference, e.g., `1 Ca 1052/25`                                                                                       |

**Optional properties**:

| Property      | Type     | Notes                        |
| ------------- | -------- | ---------------------------- |
| `author_firm` | string   | Drafting firm or party       |
| `total_pages` | int      | Page count of source PDF     |
| `source_file` | string   | Path to original PDF         |
| `ingested_at` | datetime | When ingested into the graph |

**Example**:

```cypher
(:Document {
  id: 'klageerwiderung_2026_04_09',
  document_type: 'Klageerwiderung',
  filing_date: date('2026-04-09'),
  filing_party: 'defendant',
  aktenzeichen: '1 Ca 1052/25',
  author_firm: 'Schmittel & Vogt',
  total_pages: 18,
  source_file: 'reference/klageerwiderung_2026_04_09.pdf',
  ingested_at: datetime()
})
```

### Node: `Paragraph`

A numbered paragraph within a Schriftsatz.

**Required properties**:

| Property    | Type   | Notes                                                    |
| ----------- | ------ | -------------------------------------------------------- |
| `id`        | string | Unique. Pattern: `{document_id}_p{page}_para{paragraph}` |
| `page`      | int    | ≥ 1. Page number in source document.                     |
| `paragraph` | int    | ≥ 1. Within-page paragraph number.                       |
| `text_de`   | string | Original German text.                                    |

**Optional properties**:

| Property         | Type                   | Notes                                                                                                                                                                 |
| ---------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `text_en`       | string                 | English translation (where available)                                          |
| `position`      | int                    | Monotonic 1-based order within the document                                    |
| `substantiated` | boolean                | Added during substantiation analysis                                           |
| `confidence`    | float                  | 0.0–1.0. Model confidence for substantiation.                                  |
| `embedding`     | `VECTOR<FLOAT32>(384)` | Added during embedding pipeline. Dimension matches the embedding model in use. |

**Example**:

```cypher
(:Paragraph {
  id: 'klageerwiderung_2026_04_09_p1_para2',
  page: 1,
  paragraph: 2,
  position: 2,
  text_de: 'Mittels Arbeitsvertrag vom 30.08.2024...',
  text_en: 'By employment contract dated August 30, 2024...'
})
```

### Relationship: `HAS_PARAGRAPH`

Connects a `Document` to each of its `Paragraph` nodes.

- **Direction**: `(:Document)-[:HAS_PARAGRAPH]->(:Paragraph)`
- **Cardinality**: one Document → many Paragraphs; each Paragraph belongs to exactly one Document.
- **Properties**: none.

### Relationship: `NEXT`

Connects each `Paragraph` to the one immediately following it in document order.

- **Direction**: `(:Paragraph)-[:NEXT]->(:Paragraph)`
- **Cardinality**: at most one outgoing NEXT per Paragraph; at most one incoming NEXT per Paragraph. The first paragraph in a Document has no incoming NEXT; the last has no outgoing NEXT.
- **Properties**: none.
- **Scope**: NEXT edges only connect paragraphs within the same Document. No cross-document chains.

### Node: `Assertion`

The atomic unit of analysis within a `Paragraph`. An Assertion is any atomic claim the document makes — factual, legal, evidentiary, etc. The type is captured by `classification`, not by which paragraphs do or do not yield Assertions. A single Paragraph routinely contains 1–N distinct assertions; each is analyzable independently for substantiation, contradiction, and evidentiary support.

Example: the Klageerwiderung sentence _"Frau Stahl forderte den Kläger mehrfach auf, die Zeiterfassung korrekt zu führen, und überprüfte regelmäßig die Eintragungen"_ contains two assertions:

1. Stahl made multiple requests for correct time tracking.
2. Stahl regularly reviewed the entries.

Each can be substantiated or contradicted independently.

**Required properties**:

| Property         | Type   | Notes                                                                                     |
| ---------------- | ------ | ----------------------------------------------------------------------------------------- |
| `id`             | string | Unique. Pattern: `{paragraph_id}_assertion_{n}` (n is 1-based)                            |
| `assertion_text` | string | The atomic claim, in the original language. May be lightly rephrased into canonical form. |

**Optional properties**:

| Property                | Type                   | Notes                                                                                                                                                                       |
| ----------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `assertion_text_en`     | string                 | English translation if available                                                                                                                                            |
| `classification`        | string                 | Added during the classification step. One of: `factual`, `legal`, `rhetorical`, `procedural`, `evidentiary`. Multi-label values stored as semicolon-separated string.       |
| `temporal_scope`        | string                 | One of: `specific_date`, `period`, `undated`. Indicates whether the claim refers to a single date, a range, or is unanchored.                                               |
| `temporal_value`        | date or string         | Concrete date or range expression when applicable                                                                                                                           |
| `is_negative`           | boolean                | True if the claim asserts something did _not_ happen (e.g., _"no warning was given"_). Affects contradiction detection logic.                                               |
| `substantiation_status` | string                 | One of: `substantiated`, `unsubstantiated`, `partial`.                                                                                                                      |
| `embedding`             | `VECTOR<FLOAT32>(384)` | Added during embedding pipeline                                                                                                                                             |
| `extracted_at`          | datetime               | When the assertion was extracted from its source paragraph                                                                                                                  |
| `confidence`            | float                  | 0.0–1.0. Model confidence in the extraction or classification.                                                                                                              |

### Relationship: `CONTAINS_ASSERTION`

Connects a `Paragraph` to each of its constituent `Assertion` nodes.

- **Direction**: `(:Paragraph)-[:CONTAINS_ASSERTION]->(:Assertion)`
- **Cardinality**: one Paragraph → 0..N Assertions; each Assertion belongs to exactly one Paragraph. Paragraphs containing only headers or pure rhetorical/procedural framing may yield zero Assertions.
- **Properties**: none.

### When `Assertion` nodes are created

The application-layer model (`graph.models.Assertion`) is implemented. Assertion **nodes** are written into Neo4j during pipeline step 5, which now consists of two sub-steps: **extraction** (atomize each paragraph into 0..N claims) followed by **classification** (assign each Assertion a `classification` value). Until that step runs, `Paragraph` remains the only unit of analysis populated in the graph.

## Invariants

These hold by construction (enforced by ingestion code via the Pydantic models in `graph/models.py`, not by the database in Community Edition):

1. Every `Paragraph` belongs to exactly one `Document` via `HAS_PARAGRAPH`.
2. `NEXT` edges form a single linear chain within each Document, ordered by `(page, paragraph)`.
3. `Paragraph.id` is deterministically derived from its `Document.id` plus its `(page, paragraph)` location — never random.
4. No NEXT edges cross Document boundaries.
5. `Document.filing_date` ≤ `Document.ingested_at` (a document is filed before it is ingested).
6. Every `Assertion` belongs to exactly one `Paragraph` via `CONTAINS_ASSERTION`.
7. `Assertion.id` is deterministically derived from its `Paragraph.id` plus a 1-based sequence number — never random.
8. If `Assertion.classification` is present, it is drawn from the allowed value set.

## Database-Enforced Constraints

Community Edition enforces only uniqueness. Run once after starting Neo4j:

```cypher
CREATE CONSTRAINT doc_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT para_id_unique IF NOT EXISTS
FOR (p:Paragraph) REQUIRE p.id IS UNIQUE;
```

Indexes (work in all editions):

```cypher
CREATE INDEX doc_type IF NOT EXISTS FOR (d:Document) ON (d.document_type);
CREATE INDEX doc_filing_party IF NOT EXISTS FOR (d:Document) ON (d.filing_party);
CREATE INDEX para_location IF NOT EXISTS FOR (p:Paragraph) ON (p.page, p.paragraph);
CREATE INDEX assertion_classification IF NOT EXISTS FOR (a:Assertion) ON (a.classification);
```

Vector index for paragraphs (run after embedding dimension is finalized):

```cypher
CREATE VECTOR INDEX paragraph_embeddings IF NOT EXISTS
FOR (p:Paragraph) ON (p.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 384,
  `vector.similarity_function`: 'cosine'
}};
```

## Planned Schema

The following layers are designed but not yet implemented. They are added during later pipeline stages. Document them here so application code, queries, and reviewers can anticipate the shape.

### Further planned layers

These are sketched here at the level of names and roles; full property specifications are added when implementation begins.

- **`Person`** — parties, witnesses, lawyers, HR personnel. Canonical name plus alias list for entity resolution.
- **`Event`** — dated occurrences (illness, communication, payment, system action).
- **`LegalElement`** — abstract legal categories that assertions support or undermine (Vorsatz, Abmahnung-Anforderungen, § 5 EFZG Anzeigepflicht, etc.).
- **`SUPPORTED_BY`** / **`CONTRADICTED_BY`** — semantic edges from Assertion to Document, Event, or other Assertion.
- **`MENTIONS`** — Paragraph or Assertion → Person, Event.
- **`PARTICIPATED_IN`** — Person → Event.
- **`SUPPORTS_LEGAL_ELEMENT`** — Assertion → LegalElement.

## Design Decisions

Decisions made during schema design, including alternatives considered and rejected. Useful context for anyone (human or AI) deciding whether to revisit these choices.

### Page nodes — rejected

**Question**: Should there be a `Page` node between `Document` and `Paragraph`?

**Decision**: No. Page is captured as a `Paragraph.page` attribute.

**Reasoning**: Page is metadata about where a paragraph appears, not a meaningful entity in the legal-analysis sense. No page-level metadata is currently needed (no OCR confidence, no header/footer modeling, no page-specific provenance). Page-based queries are trivial as `WHERE p.page = N` and don't benefit from graph traversal. Adding a Page node would multiply edges, add a hop to most queries, and carry no information not already in attributes.

**Revisit if**: Page-level metadata becomes relevant — for example, OCR confidence per page, scanned vs. digital provenance, page-specific OCR errors, or multi-document workflows where pages need to be cross-referenced.

### Atomic-claim granularity — `Assertion` layer instead of paragraph-as-claim

**Question**: How should we handle paragraphs that contain multiple distinct claims?

**Decision**: Introduce a dedicated `Assertion` node layer between `Paragraph` and downstream analysis. `Paragraph` remains the source-of-text unit; `Assertion` is the unit of analysis. Each `Assertion` is classified individually (factual / legal / evidentiary / …) — classification lives on `Assertion`, not on `Paragraph`.

**Alternatives considered**:

- _Treat the paragraph as the assertion unit_: simpler, but loses precision when paragraphs combine multiple claims. Substantiation and contradiction analyses lose resolution.
- _Use a flat `assertions` list property on Paragraph_: harder to attach independent edges (supported_by, contradicted_by, mentions) to each individual claim. Graph operations become awkward.
- _Classify at the paragraph level, then extract assertions only from factual paragraphs_: rejected because German pleadings routinely mix factual recitation with legal characterization inside a single Absatz, and some of the most useful contradictions to surface are between *characterizations* ("dies stellt Arbeitszeitbetrug dar" vs. plaintiff's "kein Vorsatz"). Paragraph-level pre-filtering throws those away.

**Revisit if**: Empirically, the overwhelming majority of paragraphs turn out to contain exactly one assertion. Currently expected: most paragraphs are 1 assertion, some 2–3, rarely more.

### Embedding dimension default — 384

**Question**: What embedding dimension to use as the schema default?

**Decision**: 384, matching `all-MiniLM-L6-v2` (the sentence-transformers default).

**Reasoning**: Local embedding model, no API cost, adequate quality for the entity-resolution and candidate-pair-generation tasks we need embeddings for. The vector index can be recreated with a different dimension if a larger model proves necessary.

**Revisit if**: Semantic precision requirements grow (e.g., 1024 for `BGE-large` or 1536 for `text-embedding-3-small` from OpenAI).

## Schema Evolution Log

- **2026-05-13** — Initial schema. `Document`, `Paragraph`, `HAS_PARAGRAPH`, `NEXT`. Planned: `Assertion`, `CONTAINS_ASSERTION`, plus further layers. Page node considered and rejected.
- **2026-05-13** — Application-layer Pydantic models added (`graph/models.py`) for `Document`, `Paragraph`, and `Assertion`. `Assertion` and `CONTAINS_ASSERTION` promoted from "Planned" to "Current Schema": the schema-side model exists; Neo4j nodes are still written only during pipeline step 5 (Klageerwiderung classification).
- **2026-05-13** — `classification` moved from `Paragraph` to `Assertion`. Rationale: German pleadings mix factual recitation with legal characterization inside single Absätze; classifying at the paragraph level loses too much, and useful contradictions live between characterizations as much as between bare facts. Pipeline step 5 is now: extract atomic Assertions per Paragraph → classify each Assertion. `para_classification` index dropped; `assertion_classification` index added.
