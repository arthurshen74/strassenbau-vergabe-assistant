-- 10_rag_ground_truth.sql
-- Curated RAG reference questions per project: the question, the expert's gold answer, and the
-- Fundstellen (document + page) the answer comes from. The refs drive deterministic retrieval
-- metrics (recall@k, MRR); the answer drives answer grading. A row without refs is legal — it
-- counts only toward answer grading, not retrieval scoring.
-- Mirrors the SQLAlchemy table def in server/shared/db/tables/rag_ground_truth.py and the
-- RagQuestionType / RagQuestionCategory enums (the source of truth this file follows).
-- Idempotent: safe to re-run. Run after 09.
-- Run: psql -d roadbuilders -f sql/10_rag_ground_truth.sql

CREATE TABLE IF NOT EXISTS rag_ground_truth (
    rag_ground_truth_uuid uuid NOT NULL DEFAULT gen_random_uuid()
        CONSTRAINT pk_rag_ground_truth PRIMARY KEY,
    project_uuid uuid NOT NULL
        CONSTRAINT fk_rag_ground_truth_project_uuid_projects
        REFERENCES projects (project_uuid) ON DELETE CASCADE,
    question text NOT NULL,
    gold_answer text NOT NULL,
    -- list of {document_uuid, page}: where the answer is found (page-level citations).
    refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    question_type text NOT NULL
        CONSTRAINT ck_rag_ground_truth_question_type_valid
        CHECK (question_type IN
            ('lookup', 'aggregation', 'multi_hop', 'constraint_surfacing', 'cross_doc_conditional')),
    category text NOT NULL
        CONSTRAINT ck_rag_ground_truth_category_valid
        CHECK (category IN ('kalkulator', 'bauleiter')),
    -- Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins to auth).
    created_by_user_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rag_ground_truth_project_uuid
    ON rag_ground_truth (project_uuid);
