# Canonical Data Model

**This document is the single source of truth for entity names, fields, types, and cross-store
identity in Roadbuilders Assistant.** Where any other document disagrees with this one on a class name, a field name, a column
type, or a key, **this document wins.** The other docs keep their prose (the _why_ and the _how_);
this doc owns the _what is it called and what shape is it_.

# Naming & typing conventions

These rules are non-negotiable; they are how the ambiguity gets removed.

- **Postgres** — tables and columns are `snake_case`, plural table names (`projects`,
  `eval_items`). Surrogate primary keys are named `{singular_table}_uuid` (`project_uuid`,
  `eval_item_uuid`, `prompt_version_uuid`) — **not** `id`. Type is `UUID` with
  `server_default gen_random_uuid()`. Timestamps are `TIMESTAMPTZ`, `server_default now()`;
  mutable rows also carry `updated_at` with `onupdate now()`.
- **Pydantic domain models** — `PascalCase` class per aggregate, fields `snake_case` matching the
  column names exactly. Each aggregate has a `New{Entity}` create-model (no surrogate/timestamps)
  and an `{Entity}` read-model (all columns). `ConfigDict(extra="forbid")` everywhere.
- **API DTOs** — `PascalCase` with a `DTO` / `Create` / `Read` / `Update` suffix
  (`ProjectDTO`, `ProjectCreateDTO`, `PromptRead`). They are a **separate** type family from domain
  models and may expose a narrower field set.
- **TypeScript** — generated into `ui/src/types/generated.ts` from the DTOs; never hand-edited.
  Field names stay `snake_case` (they mirror the JSON wire shape).
- **Elasticsearch** — index and field names are `snake_case` (`roadbuilders_text`, `project_uuid`).
- **German domain terms are never translated.** `lv_item` not `bill_item`, `kurztext` not
  `short_text`, `vergabe_stelle` not `awarding_authority`, `menge`/`einheit`/`positionstyp` as-is.
  `GLOSSARY.md` is the source of truth for spelling.

# Data Model/Schema

- Every entity on this schema has at least a domain model (Pydantic, implementation agnostic)
- Every entity has an annotation about what implementations to make in addition to the domain model. It could be "postgres", "elasticsearch" or "postgres_elasticsearch".
- The annotation indicates where the implentations are targeted.
- If a field annotation has {implementation_targets}\_only, then that field goes only for the targeted implentations. otherwise, assume it goes on all defined implementations.

```mermaid
classDiagram

   class Project {
        <<postgres>>
        +uuid project_uuid PK
        +text vergabe_id
        +text project_name
        +text project_description
        +text vergabestelle
        +timestamptz created_at postgres_only
        +timestamptz updated_at postgres_only
    }

    class Document {
        <<postgres>>
        +uuid document_uuid PK
        +uuid project_uuid FK
        +text document_type LV_DOCUMENT or PROSE_DOCUMENT
        +text file_name
        +text? document_description
        +int number_of_pages
        +timestamptz created_at postgres_only
        +timestamptz updated_at postgres_only
    }

    note for SourceLine "This is where canonical prose body text lives."
    class SourceLine {
        <<postgres>>
        +uuid source_line_uuid PK
        +uuid document_uuid FK, UK
        +int line_id UK
        +int page
        +tuple~float float float float~ bbox
        +str line_text
    }

    Document *-- SourceLine : one_to_many

    class Thumbnail {
        <<postgres>>
        +uuid thumbnail_uuid PK
        +uuid document_uuid FK
        +int page_number
        +text object_key
        +text bucket
        +int width
        +int height
        +text content_type
        +timestamptz created_at postgres_only
    }

    class IngestJob {
        <<postgres>>
        +uuid job_uuid PK
        +uuid document_uuid FK
        +text status
        +timestamptz created_at postgres_only
        +timestamptz updated_at postgres_only
    }
    note for IngestJob "SELECT ...SKIP LOCKED"

    class IngestJobEvent {
        <<postgres>>
        +uuid job_event_uuid PK
        +uuid job_uuid FK
        +text event
        +text? pipeline_phase
        +text message
        +timestamptz ts
    }

    Project    *-- Document         : one_contains_many
    Document   *-- Thumbnail        : one_has_many
    Document   *-- IngestJob         : one_processed_by_many
    IngestJob  *-- IngestJobEvent   : one_logs_many

    class LVItem {
        <<postgres>>
        +uuid lv_item_uuid PK
        +uuid document_uuid UK, FK
        +str oz UK
        +str kurztext
        +str langtext
        +number menge
        +str einheit
        +str positionstyp
        +int level
        +str? stl_nr
        +str? hinweis
        +str? langtext_resolved "linked oz body + the delta, composed at ingestion"
        +str? linked_oz "for linked oz"
        +str? prev_oz
        +str? next_oz
        +str? parent_oz
        +list~uuid~ source_lines
        +timestamptz last_ingestion postgres_only
    }

    Document *-- LVItem : one_to_many
    SourceLine *-- LVItem: one_to_many

    class SimpleChunk {
        <<elasticsearch>>
        +uuid chunk_uuid PK
        +uuid project_uuid "Denormalized; project scoping"
        +uuid source_doc_uuid "Document or LVItem; resolved by source_doc_type"
        +str source_doc_type "LV_ITEM | DOCUMENT"
        +str source_doc_field "e.g. langtext or langtext_resolved, kurztext, sourcelines.line_text"
        +str source_doc_language "e.g. en, de, fr, cn"
        +list~int~ source_doc_pages "chunks may cross pages"
        +int chunk_index "order within source_doc_field"
        +str oz "denormalized; LV_Item only, else null"
        +str stl_nr "denormalized; LV_Item only, for dedup"
        +uuid project_uuid "denormalized; project scoping"
        +str chunk_text "the embedded text"
        +vector embedding
        +str embedding_model "model/version that produced the vector"
    }

    SimpleChunk ..> Document : DOCUMENT
    SimpleChunk ..> LVItem : LV_ITEM

```
