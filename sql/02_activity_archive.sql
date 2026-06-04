-- 02_activity_archive.sql
-- Cold archive for the ingestion activity stream (A2 follow-on). Idempotent; run after 01.
-- The worker moves aged-out rows from ingestion_activity_log into this table instead of deleting
-- them, so the active table stays small while a document's full history is preserved.
-- id mirrors the original active-table id (plain bigint, not identity) so the move preserves it.

CREATE TABLE IF NOT EXISTS ingestion_activity_log_archive (
    id            bigint PRIMARY KEY,
    job_uuid      uuid NOT NULL REFERENCES ingest_jobs(job_uuid)    ON DELETE CASCADE,
    document_uuid uuid NOT NULL REFERENCES documents(document_uuid) ON DELETE CASCADE,
    worker_id     text NOT NULL,
    phase         text,
    message       text NOT NULL,
    ts            timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_activity_archive_document_id
    ON ingestion_activity_log_archive (document_uuid, id);
