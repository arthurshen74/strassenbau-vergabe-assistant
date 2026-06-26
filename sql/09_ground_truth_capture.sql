-- 09_ground_truth_capture.sql
-- Ground-truth capture for the EKT calculator's variable extraction, built from the Gate B review:
--   1. calculation_ground_truth: the expert-confirmed answer for one LV position (leistung_key,
--      bauverfahren_key, and the endorsed value per reviewed variable), saved when the Kalkulator
--      ticks "save as ground truth" at Gate B. One row per (project, position); a re-save upserts.
--   2. variable_corrections: an append-only log of every Gate B override — the model's proposal
--      (value + provenance + confidence) vs the value the Kalkulator set, with an optional reason.
--      The reason tag separates model errors from expert judgement so eval metrics stay valid.
-- Mirrors the SQLAlchemy table defs in
-- server/shared/db/tables/{calculation_ground_truth,variable_corrections}.py and the
-- VariableCorrectionReason enum (the source of truth this file follows).
-- Idempotent: safe to re-run. Run after 08.
-- Run: psql -d roadbuilders -f sql/09_ground_truth_capture.sql

-- 1. calculation_ground_truth: the curated gold set (latest per position).
CREATE TABLE IF NOT EXISTS calculation_ground_truth (
    ground_truth_uuid uuid NOT NULL DEFAULT gen_random_uuid()
        CONSTRAINT pk_calculation_ground_truth PRIMARY KEY,
    project_uuid uuid NOT NULL
        CONSTRAINT fk_calculation_ground_truth_project_uuid_projects
        REFERENCES projects (project_uuid) ON DELETE CASCADE,
    lv_item_uuid uuid NOT NULL
        CONSTRAINT fk_calculation_ground_truth_lv_item_uuid_lv_items
        REFERENCES lv_items (lv_item_uuid) ON DELETE CASCADE,
    source_conversation_uuid uuid
        CONSTRAINT fk_calculation_ground_truth_source_conversation_uuid_conversations
        REFERENCES conversations (conversation_uuid) ON DELETE SET NULL,
    oz text,
    leistung_key text NOT NULL,
    bauverfahren_key text,
    gold_variables jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins to auth).
    created_by_user_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_calculation_ground_truth_project_uuid UNIQUE (project_uuid, lv_item_uuid)
);
CREATE INDEX IF NOT EXISTS ix_calculation_ground_truth_project_uuid
    ON calculation_ground_truth (project_uuid);

-- 2. variable_corrections: append-only override log (error-analysis telemetry).
CREATE TABLE IF NOT EXISTS variable_corrections (
    correction_uuid uuid NOT NULL DEFAULT gen_random_uuid()
        CONSTRAINT pk_variable_corrections PRIMARY KEY,
    project_uuid uuid NOT NULL
        CONSTRAINT fk_variable_corrections_project_uuid_projects
        REFERENCES projects (project_uuid) ON DELETE CASCADE,
    lv_item_uuid uuid
        CONSTRAINT fk_variable_corrections_lv_item_uuid_lv_items
        REFERENCES lv_items (lv_item_uuid) ON DELETE SET NULL,
    oz text,
    conversation_uuid uuid
        CONSTRAINT fk_variable_corrections_conversation_uuid_conversations
        REFERENCES conversations (conversation_uuid) ON DELETE SET NULL,
    leistung_key text,
    bauverfahren_key text,
    variable_name text NOT NULL,
    proposed_wert text,
    proposed_quelle text,
    proposed_konfidenz text,
    proposed_beleg text,
    final_wert text NOT NULL,
    reason text,
    note text,
    -- Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins to auth).
    created_by_user_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_variable_corrections_correction_reason_valid
        CHECK (reason IS NULL OR reason IN
            ('falscher_wert', 'falsche_quelle', 'einheit', 'kontext_fehlt', 'kalkulator_ermessen', 'sonstiges'))
);
CREATE INDEX IF NOT EXISTS ix_variable_corrections_project_uuid
    ON variable_corrections (project_uuid);
CREATE INDEX IF NOT EXISTS ix_variable_corrections_variable_name
    ON variable_corrections (variable_name);
