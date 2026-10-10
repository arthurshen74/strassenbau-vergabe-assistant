-- 19_rag_query_versions.sql
-- rag_query_versions: the versioned, user-editable RAG queries that fill the project header
-- fields after a ZIP-first ingest. Append-only like prompt_versions: one row per
-- (query_key, language, version), version counted per (query_key, language). query_text is the
-- retrieval question (embedding + BM25 input), answer_instruction the output rule for the
-- synthesis LLM. Mirrors server/shared/db/tables/rag_query_versions.py and the ProjectInfoQuery
-- enum (the source of truth this file follows).
-- Idempotent: safe to re-run. Run after 18.
-- Run: psql -d roadbuilders -f sql/19_rag_query_versions.sql
-- Then seed: PYTHONPATH=server uv run python -m scripts.seed.rag_queries

CREATE TABLE IF NOT EXISTS rag_query_versions (
    rag_query_version_uuid uuid NOT NULL DEFAULT gen_random_uuid()
        CONSTRAINT pk_rag_query_versions PRIMARY KEY,
    query_key text NOT NULL
        CONSTRAINT ck_rag_query_versions_query_key_valid
        CHECK (query_key IN ('project-description', 'project-massnahmenummer', 'project-name',
                             'project-vergabenummer', 'project-bauleistung',
                             'project-location', 'project-vergabestelle')),
    -- ISO 639-1, lower case.
    language text NOT NULL
        CONSTRAINT ck_rag_query_versions_language_valid
        CHECK (language ~ '^[a-z]{2}$'),
    version integer NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    query_text text NOT NULL,
    answer_instruction text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_rag_query_versions_query_key
        UNIQUE (query_key, language, version)
);
