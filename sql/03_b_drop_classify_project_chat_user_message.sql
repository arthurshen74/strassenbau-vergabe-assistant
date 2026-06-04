-- 03_b_drop_classify_project_chat_user_message.sql
-- Removes the deprecated classify_project_chat_user_message prompt type, which is
-- no longer in the PromptType enum. Deletes its rows, then tightens both
-- prompt_type CHECK constraints to the enum-exact set (matching 00_main_seed).
-- Run after 03_a_add_aggregate_lv_membership.sql. Idempotent: safe to re-run.
-- Run: psql -d roadbuilders -f sql/03_b_drop_classify_project_chat_user_message.sql
-- Historical prompt_execution_log rows keep their prompt_type text and are untouched.

DELETE FROM prompt_versions WHERE prompt_type = 'classify_project_chat_user_message';
DELETE FROM conversations WHERE prompt_type = 'classify_project_chat_user_message';

ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name'));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name'));
