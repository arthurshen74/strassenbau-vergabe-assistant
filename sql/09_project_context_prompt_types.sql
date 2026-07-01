-- 09_project_context_prompt_types.sql
-- Widen both prompt_type CHECK constraints for the new project-context resolution prompt:
-- project_context_resolve (the dedicated PROJECT_CONTEXT_RESOLVE synthesis over hybrid-RAG chunks).
-- create_all(checkfirst) never alters an existing table, so the enum-derived CHECK goes stale every
-- time PromptType grows; seeding the new prompt (python -m scripts.seed.prompts) fails the CHECK as
-- an IntegrityError until this runs.
-- Value lists mirror the SQLAlchemy table defs and the PromptType enum (the source of truth), and
-- retain the legacy ekt_* values 08 kept so an already-migrated DB's existing rows still satisfy the
-- constraint. conversations is widened in tandem with prompt_versions (as in 08), keeping a
-- migrated DB's CHECK identical to what a fresh create_all builds; no conversation uses the new
-- value (it is a structured prompt, not a conversation discriminator).
-- Constraints only, no seed: the prompt is seeded from project_context_resolve.prompt via
-- `python -m scripts.seed.prompts`.
-- Idempotent: safe to re-run. Run after 08.
-- Run: psql -d roadbuilders -f sql/09_project_context_prompt_types.sql

ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'project_context_resolve', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'project_context_resolve', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));
