-- 10_katalog_chat_prompt_type.sql
-- Widen both prompt_type CHECK constraints for katalog_chat (the read-only catalog chat's
-- conversation discriminator; it lands in conversations.prompt_type). create_all(checkfirst) never
-- alters an existing table, so the enum-derived CHECK goes stale every time PromptType grows;
-- inserting a katalog_chat conversation fails the CHECK as an IntegrityError until this runs.
-- Value lists mirror the current PromptType enum (the source of truth) and retain the legacy ekt_*
-- values earlier migrations kept so an already-migrated DB's existing rows still satisfy the
-- constraint. Also (re)adds rezept_autor, which its own change omitted a migration for.
-- katalog_chat is a conversation discriminator (no seeded prompt), so no prompt seed follows.
-- conversations is widened in tandem with prompt_versions, keeping a migrated DB identical to what a
-- fresh create_all builds. Idempotent: safe to re-run. Run after 09.
-- Run: psql -d roadbuilders -f sql/10_katalog_chat_prompt_type.sql

ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'rezept_autor', 'katalog_chat', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'project_context_resolve', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'rezept_autor', 'katalog_chat', 'ekt_leistung_classify', 'ekt_chat_values', 'ekt_langtext_extract', 'ekt_output_narrate', 'project_context_resolve', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));
