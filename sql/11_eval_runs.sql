-- 11_eval_runs.sql
-- The eval-run queue: eval_runs is both the job queue (same competing-consumer lease mechanics
-- as ingest_jobs: SKIP LOCKED claim, locked_by/locked_at lease, attempts budget) and the record
-- of each run (summary metrics keyed to the prompt versions exercised). eval_run_events is the
-- append-only progress feed the UI polls; eval_results holds the per-item drill-down.
-- Mirrors server/shared/db/tables/{eval_runs,eval_run_events,eval_results}.py and the
-- EvalRunKind / EvalRunStatus enums (the source of truth this file follows).
-- Idempotent: safe to re-run. Run after 10.
-- Run: psql -d roadbuilders -f sql/11_eval_runs.sql

CREATE TABLE IF NOT EXISTS eval_runs (
    eval_run_uuid uuid NOT NULL DEFAULT gen_random_uuid()
        CONSTRAINT pk_eval_runs PRIMARY KEY,
    kind text NOT NULL
        CONSTRAINT ck_eval_runs_kind_valid
        CHECK (kind IN ('calculator_gold', 'chat_values', 'rag_retrieval', 'rag_answers')),
    -- Scope for project-bound kinds (calculator_gold, rag_*); chat_values runs without one.
    project_uuid uuid
        CONSTRAINT fk_eval_runs_project_uuid_projects
        REFERENCES projects (project_uuid) ON DELETE CASCADE,
    -- Kind-specific knobs (abs_tol, limit, dataset ...).
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'queued'
        CONSTRAINT ck_eval_runs_status_valid
        CHECK (status IN ('queued', 'running', 'done', 'failed')),
    -- Lease for crash recovery (see ingest_jobs): reclaimable once expired, attempts bounds retries.
    locked_at timestamptz,
    locked_by text,
    attempts integer NOT NULL DEFAULT 0,
    error text,
    summary jsonb,
    prompt_versions jsonb,
    -- Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins to auth).
    created_by_user_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_eval_runs_project_uuid ON eval_runs (project_uuid);
CREATE INDEX IF NOT EXISTS ix_eval_runs_status_locked_at ON eval_runs (status, locked_at);

CREATE TABLE IF NOT EXISTS eval_run_events (
    event_uuid uuid NOT NULL DEFAULT gen_random_uuid()
        CONSTRAINT pk_eval_run_events PRIMARY KEY,
    eval_run_uuid uuid NOT NULL
        CONSTRAINT fk_eval_run_events_eval_run_uuid_eval_runs
        REFERENCES eval_runs (eval_run_uuid) ON DELETE CASCADE,
    message text NOT NULL,
    ts timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_eval_run_events_eval_run_uuid ON eval_run_events (eval_run_uuid);

CREATE TABLE IF NOT EXISTS eval_results (
    result_uuid uuid NOT NULL DEFAULT gen_random_uuid()
        CONSTRAINT pk_eval_results PRIMARY KEY,
    eval_run_uuid uuid NOT NULL
        CONSTRAINT fk_eval_results_eval_run_uuid_eval_runs
        REFERENCES eval_runs (eval_run_uuid) ON DELETE CASCADE,
    item_id text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_eval_results_eval_run_uuid ON eval_results (eval_run_uuid);
