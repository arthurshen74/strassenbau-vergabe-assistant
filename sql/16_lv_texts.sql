-- 16_lv_texts.sql
-- lv_texts: the LV document's non-position texts (Vorbemerkungen / Nachtext as ADD_TEXT, Hinweise
-- as REMARK), parsed from GAEB D83/X83 alongside lv_items. Rows are replaced wholesale on every
-- re-ingest (no natural key), so there is no unique constraint beyond the PK; the ES LV_TEXT
-- chunks are keyed by lv_text_uuid. Mirrors server/shared/db/tables/lv_texts.py and the
-- LVTextKind / LVTextPlacement enums (the source of truth this file follows). Column `index` is
-- a reserved word but unquoted creation works in Postgres; it is the per-kind ordinal, `sequence`
-- the overall document order.
-- Idempotent: safe to re-run. Run after 15.
-- Run: psql -d roadbuilders -f sql/16_lv_texts.sql

CREATE TABLE IF NOT EXISTS lv_texts (
    lv_text_uuid uuid NOT NULL DEFAULT gen_random_uuid()
        CONSTRAINT pk_lv_texts PRIMARY KEY,
    document_uuid uuid NOT NULL
        CONSTRAINT fk_lv_texts_document_uuid_documents
        REFERENCES documents (document_uuid) ON DELETE CASCADE,
    kind text NOT NULL
        CONSTRAINT ck_lv_texts_lv_text_kind_valid
        CHECK (kind IN ('ADD_TEXT', 'REMARK')),
    -- Only ADD_TEXT carries a placement (Vortext 'before' / Nachtext 'after'); REMARK is NULL.
    placement text
        CONSTRAINT ck_lv_texts_lv_text_placement_valid
        CHECK (placement IS NULL OR placement IN ('before', 'after')),
    -- OZ of the enclosing LV node (Los / Titel / Position); NULL for document-level texts.
    parent_oz text,
    index integer NOT NULL,
    sequence integer NOT NULL,
    oz text,
    heading text,
    body text NOT NULL,
    last_ingestion timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_lv_texts_document_uuid ON lv_texts (document_uuid);
