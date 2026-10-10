-- 20_project_info_jobs.sql
-- project_info_jobs: one Projektinfo extraction per row. The worker claims a job only once
-- the project has no queued or running ingest job, runs the project-info RAG queries and
-- writes the found values into the projects header columns. Same lease mechanics as
-- ingest_jobs. Mirrors server/shared/db/tables/project_info_jobs.py (the source of truth this
-- file follows).
-- Idempotent: safe to re-run. Run after 19.
-- Run: psql -d roadbuilders -f sql/20_project_info_jobs.sql

CREATE TABLE IF NOT EXISTS project_info_jobs (
	job_uuid UUID DEFAULT gen_random_uuid() NOT NULL,
	project_uuid UUID NOT NULL,
	language TEXT NOT NULL,
	overwrite BOOLEAN DEFAULT false NOT NULL,
	status TEXT DEFAULT 'queued' NOT NULL,
	locked_at TIMESTAMP WITH TIME ZONE,
	locked_by TEXT,
	attempts INTEGER DEFAULT 0 NOT NULL,
	error TEXT,
	result JSONB,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_project_info_jobs PRIMARY KEY (job_uuid),
	CONSTRAINT ck_project_info_jobs_status_valid CHECK (status IN ('queued', 'running', 'done', 'failed')),
	CONSTRAINT fk_project_info_jobs_project_uuid_projects FOREIGN KEY(project_uuid) REFERENCES projects (project_uuid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_project_info_jobs_project_uuid ON project_info_jobs (project_uuid);
CREATE INDEX IF NOT EXISTS ix_project_info_jobs_status_locked_at ON project_info_jobs (status, locked_at);
