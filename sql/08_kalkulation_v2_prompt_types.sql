-- 08_kalkulation_v2_prompt_types.sql
-- Widen both prompt_type CHECK constraints for the four kalkulation_v2 (live graph) prompt types:
-- ekt_leistung_classify, ekt_chat_values, ekt_langtext_extract, ekt_output_narrate.
-- create_all(checkfirst) never alters an existing table, so the enum-derived CHECK goes stale every
-- time PromptType grows; seeding a new prompt fails the CHECK as an IntegrityError until this runs.
-- Value lists mirror the SQLAlchemy table defs and the PromptType enum (the source of truth).
-- Constraints only, no seed: the prompts are seeded from the ekt_*.prompt files via
-- `python -m scripts.seed.prompts`.
-- Idempotent: safe to re-run. Run after 07.
-- Run: psql -d roadbuilders -f sql/08_kalkulation_v2_prompt_types.sql

ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));
