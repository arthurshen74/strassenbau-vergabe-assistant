-- 01_ingest_crash_recovery.sql
-- Incremental migration for ingest crash recovery (A2). Idempotent: safe to re-run.
-- Run against an existing database after 00_main_seed.sql:  psql -d roadbuilders -f sql/01_ingest_crash_recovery.sql
-- Fresh databases get this from the SQLAlchemy metadata via scripts/bootstrap_tables.py; the
-- Table definitions in server/shared/db/tables/ are the source of truth this file mirrors.

-- ingest_jobs: lease (locked_at / locked_by) + bounded-retry (attempts) bookkeeping.
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS locked_at timestamptz;
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS locked_by text;
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS attempts  integer NOT NULL DEFAULT 0;

-- Lets claim_next find expired RUNNING jobs (and park_exhausted scan them) without a seq scan.
CREATE INDEX IF NOT EXISTS ix_ingest_jobs_status_locked_at ON ingest_jobs (status, locked_at);

-- ingestion_activity_log: granular liveness + UI terminal feed, tagged with worker_id.
CREATE TABLE IF NOT EXISTS ingestion_activity_log (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_uuid      uuid NOT NULL REFERENCES ingest_jobs(job_uuid)    ON DELETE CASCADE,
    document_uuid uuid NOT NULL REFERENCES documents(document_uuid) ON DELETE CASCADE,
    worker_id     text NOT NULL,
    phase         text,
    message       text NOT NULL,
    ts            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_activity_job_id ON ingestion_activity_log (job_uuid, id);
