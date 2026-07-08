-- 14_katalog_handbuch_prompt_type.sql
-- Widen both prompt_type CHECK constraints for katalog_handbuch (the katalog_chat agent's system
-- prompt, now a SEEDED prompt loaded via get_latest instead of a hardcoded constant). Phase 4 of the
-- Rezept redesign (REZEPT_REDESIGN_PLAN §3). create_all(checkfirst) never alters an existing table,
-- so the enum-derived CHECK goes stale; seeding the new prompt (scripts.seed.prompts) fails the
-- prompt_versions CHECK as an IntegrityError until this runs. Value lists mirror the current
-- PromptType enum and retain the legacy ekt_* values earlier migrations kept, so an already-migrated
-- DB's existing rows still satisfy the constraint. conversations is widened in tandem, keeping a
-- migrated DB identical to what a fresh create_all builds. Idempotent: safe to re-run. Run after 13.
-- Run: psql -d roadbuilders -f sql/14_katalog_handbuch_prompt_type.sql

ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'rezept_autor', 'katalog_chat', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'project_context_resolve', 'katalog_handbuch', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'rezept_autor', 'katalog_chat', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'project_context_resolve', 'katalog_handbuch', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));
