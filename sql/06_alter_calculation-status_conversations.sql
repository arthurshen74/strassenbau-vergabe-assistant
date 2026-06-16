-- 06_alter_calculation-status_conversations.sql
-- Add the 'awaiting_start' calculation_status value: an ekt_calculator conversation now opens as a
-- chat gate (the user discusses the LV position or asks to run it) before the graph starts, so the
-- lifecycle is awaiting_start -> running -> awaiting_input -> complete/failed.
-- Mirrors the CalculationStatus enum and the conversations table def in
-- server/shared/db/tables/conversations.py (the source of truth this file follows). The constraint
-- name is the metadata naming convention's ck_<table>_<constraint> form (see shared/db/metadata.py).
-- Idempotent: safe to re-run. Run after 05.
-- Run: psql -d roadbuilders -f sql/06_alter_calculation-status_conversations.sql

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_calculation_status_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_calculation_status_valid
	CHECK (calculation_status IS NULL OR calculation_status IN ('awaiting_start', 'running', 'awaiting_input', 'complete', 'failed'));
