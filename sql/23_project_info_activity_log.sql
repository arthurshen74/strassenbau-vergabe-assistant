-- 23_project_info_activity_log.sql
-- project_info_activity_log: granular activity lines of a Projektinfo job (claim, retrieve,
-- synthesize, write), the counterpart of ingestion_activity_log for project_info_jobs. The
-- worker's buffered flushes write it and refresh the job's lease; the ingest console shows
-- each job's latest line and tails it in the activity terminal. Pruned by the worker after
-- settings.activity_retention_hours; there is no archive table. Mirrors
-- server/shared/db/tables/project_info_activity_log.py (the source of truth this file
-- follows).
-- Idempotent: safe to re-run. Run after 22.
-- Run: psql -d roadbuilders -f sql/23_project_info_activity_log.sql

CREATE TABLE IF NOT EXISTS project_info_activity_log (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	job_uuid UUID NOT NULL,
	project_uuid UUID NOT NULL,
	worker_id TEXT NOT NULL,
	phase TEXT,
	message TEXT NOT NULL,
	ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_project_info_activity_log PRIMARY KEY (id),
	CONSTRAINT fk_project_info_activity_log_job_uuid_project_info_jobs FOREIGN KEY(job_uuid) REFERENCES project_info_jobs (job_uuid) ON DELETE CASCADE,
	CONSTRAINT fk_project_info_activity_log_project_uuid_projects FOREIGN KEY(project_uuid) REFERENCES projects (project_uuid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_project_info_activity_job_id ON project_info_activity_log (job_uuid, id);
