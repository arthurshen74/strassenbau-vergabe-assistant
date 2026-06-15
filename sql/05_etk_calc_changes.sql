-- 05_etk_calc_changes.sql
-- Schema changes for the interactive EKT calculator feature (conversation-backed runs):
--   1. Add the ekt_calculator prompt type to both prompt_type CHECK constraints, so a calculator
--      run can own a conversations row (the run is surfaced in, and continued from, the chat UI).
--   2. Add conversations.calculation_status to track an ekt_calculator run's lifecycle
--      (running -> awaiting_input -> complete/failed); NULL for non-calculator conversations.
--   3. Tag prompt_execution_log rows with the owning conversation_uuid (the calculator's LLM calls
--      now route through LLMClient). SET NULL so the log outlives a deleted conversation.
-- Mirrors the SQLAlchemy table defs in server/shared/db/tables/{conversations,prompt_execution_log}.py
-- and the PromptType / CalculationStatus enums (the source of truth this file follows).
-- Idempotent: safe to re-run. Run after 04.
-- Run: psql -d roadbuilders -f sql/05_etk_calc_changes.sql

-- 1. Widen both prompt_type CHECK constraints to allow ekt_calculator.
ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator'));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator'));

-- 2. conversations.calculation_status: ekt_calculator run lifecycle; NULL for other conversations.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS calculation_status text;
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_calculation_status_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_calculation_status_valid
	CHECK (calculation_status IS NULL OR calculation_status IN ('running', 'awaiting_input', 'complete', 'failed'));

-- 2b. conversations.lv_item_uuid: the LV position an ekt_calculator run targets, so the run can be
-- (re)started and streamed by conversation_uuid alone. NULL for non-calculator conversations.
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS lv_item_uuid uuid REFERENCES lv_items(lv_item_uuid) ON DELETE SET NULL;

-- 3. prompt_execution_log.conversation_uuid: attribute calculator (and chat) LLM calls.
ALTER TABLE prompt_execution_log
    ADD COLUMN IF NOT EXISTS conversation_uuid uuid REFERENCES conversations(conversation_uuid) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_prompt_execution_log_conversation_uuid
    ON prompt_execution_log (conversation_uuid);
