-- 21_project_info_resolve_prompt_type.sql
-- Widen both prompt_type CHECK constraints for project_info_resolve (the seeded synthesis
-- prompt the project-info job loads via get_latest). create_all(checkfirst) never alters an
-- existing table, so seeding the new prompt (scripts.seed.prompts) fails the prompt_versions
-- CHECK until this runs. Value lists are the 15_ner_fehleranalyse_prompt_type.sql lists plus
-- the new value; conversations is widened in tandem, keeping a migrated DB identical to what a
-- fresh create_all builds. Idempotent: safe to re-run. Run after 20.
-- Run: psql -d roadbuilders -f sql/21_project_info_resolve_prompt_type.sql
-- Then seed: PYTHONPATH=server uv run python -m scripts.seed.prompts

ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'rezept_autor', 'katalog_chat', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'project_context_resolve', 'katalog_handbuch', 'ner_fehleranalyse', 'project_info_resolve', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'rezept_autor', 'katalog_chat', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'project_context_resolve', 'katalog_handbuch', 'ner_fehleranalyse', 'project_info_resolve', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));
