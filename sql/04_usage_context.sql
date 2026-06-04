-- 04_usage_context.sql
-- Tag OpenRouter usage with the owning document (ingestion calls: LV parse + embeddings) and the
-- conversation (every OpenRouter call made during a project-chat turn: answer generation, query
-- expansion, retrieval embeddings, and reranking). Idempotent; run after 02. SET NULL so cost
-- history outlives a deleted document/conversation. The SQLAlchemy Table def in
-- server/shared/db/tables/openrouter_usage.py is the source of truth this mirrors.

ALTER TABLE openrouter_usage
    ADD COLUMN IF NOT EXISTS document_uuid uuid REFERENCES documents(document_uuid) ON DELETE SET NULL;
ALTER TABLE openrouter_usage
    ADD COLUMN IF NOT EXISTS conversation_uuid uuid REFERENCES conversations(conversation_uuid) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_openrouter_usage_document_uuid
    ON openrouter_usage (document_uuid);
CREATE INDEX IF NOT EXISTS ix_openrouter_usage_conversation_uuid
    ON openrouter_usage (conversation_uuid);
