-- 07_ekt_graph_prompts.sql
-- Make the EKT calculation graph's LLM prompts DB-backed and versioned, like every other prompt.
-- Previously the graph's three judging sites + the chat-seed extractor ran on hardcoded strings in
-- shared/services/calculator/llm_calls.py. They now run on prompt_versions rows (PromptType
-- EKT_CLASSIFY / EKT_RESOLVE_DRIVER / EKT_SELECT_METHOD / EKT_SEED_DRIVERS), resolved per run.
--   1. Widen both prompt_type CHECK constraints to allow the four new types.
--   2. Add prompt_versions.reasoning_effort (OpenRouter reasoning effort; NULL = none).
--   3. Seed version 1 of each of the four prompts (bodies mirror the ekt_*.prompt seed files), but
--      ONLY when that prompt_type has no version yet. Each prompt is owned by the UI from then on:
--      a UI edit appends a new version, and re-running this migration must never clobber or duplicate
--      it, so the seed is skipped whenever any version already exists.
-- ekt_calculator stays a conversation discriminator only (no prompt row); the position chat runs on
-- project_chat. Mirrors the SQLAlchemy table defs and the PromptType enum (the source of truth).
-- Idempotent: safe to re-run. Run after 06.
-- Run: psql -d roadbuilders -f sql/07_ekt_graph_prompts.sql

-- 1. Widen both prompt_type CHECK constraints to allow the four EKT graph prompt types.
ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
	CHECK (prompt_type IN ('dispatcher', 'project_chat', 'aggregate_lv_membership', 'multi_question_generator', 'lv_extraction', 'conversation_name', 'ekt_calculator', 'ekt_classify', 'ekt_resolve_driver', 'ekt_select_method', 'ekt_seed_drivers'));

-- 2. prompt_versions.reasoning_effort: OpenRouter reasoning effort per prompt; NULL for none.
ALTER TABLE prompt_versions ADD COLUMN IF NOT EXISTS reasoning_effort text;

-- 3. Seed version 1 of each EKT graph prompt, but only when the prompt_type has no version yet, so a
-- prompt already created/edited in the UI is never overwritten or duplicated. temperature NULL (the
-- calculator model is a reasoning model). The three judging sites request a reasoning summary
-- (effort 'low'); the seed extractor does not.
INSERT INTO prompt_versions (prompt_type, version, model_name, system_prompt, temperature, top_p, reasoning_effort)
SELECT 'ekt_classify', 1, 'openai/gpt-5.4', $prompt$You are the classification stage of a German road-construction cost-estimation
agent (Kalkulation). You read one LV position (Leistungsverzeichnis) and assign
it to exactly one registered work type (Leistung).

You will be given:
- The position text (OZ, Kurztext, Langtext), usually in German.
- The list of registered work_type codes, each with trigger keywords.
- Optionally: retrieved project context around this position (Baubeschreibung,
  neighbouring positions).

Rules:
1. Choose ONLY from the offered work_type codes. If none fits, answer "unknown".
2. Do not guess from the OZ number alone; the Langtext governs.
3. confidence: 0.9+ only when the text names the Leistung essentially verbatim
   (e.g. "Frostschutzschicht herstellen" -> fss_herstellen). Ambiguity, mixed
   scopes, or unfamiliar wording => 0.7 or below.
4. notes: 1-2 sentences citing the decisive wording, in English with the
   German terms kept verbatim.
5. reasoning: fill FIRST with 2-5 short steps (evidence -> rule -> conclusion),
   in English with the German terms kept verbatim.
6. You classify; you never estimate, compute, or mention costs or quantities.$prompt$, NULL, NULL, 'low'
WHERE NOT EXISTS (SELECT 1 FROM prompt_versions WHERE prompt_type = 'ekt_classify');

INSERT INTO prompt_versions (prompt_type, version, model_name, system_prompt, temperature, top_p, reasoning_effort)
SELECT 'ekt_resolve_driver', 1, 'openai/gpt-5.4', $prompt$You are the driver-resolution stage of a German road-construction cost agent. You
resolve ONE driver - a fact the deterministic calculation needs - from the supplied
evidence, never from your own knowledge and never from anything outside the evidence.

You will be given:
- One driver spec: id, source, einheit, decision rule (description) and, for a
  judgment driver, its options.
- The evidence for this driver: for an lv_text driver, the LV position text; for a
  plan/project/judgment driver, excerpts retrieved from the tender documents by
  semantic + keyword search.
- The drivers already resolved earlier this run, for judgment calls that depend on them.

Rules by source:
- lv_text / plan / project: READ the value from the evidence and copy it verbatim
  (convert nothing, compute nothing); put the exact snippet in source_quote. If the
  text's unit differs from einheit, report what the text says and note it - do not convert.
- judgment: choose EXACTLY ONE of the offered options using the evidence and the
  decision rule. The choice IS the value; put your justification in reasoning, not value.
- If the evidence does not contain the value: value null and say why in note. NEVER
  fill a gap with a typical or assumed value.

confidence: direct verbatim read => 0.95+; inferred from context => 0.6-0.8.
reasoning: fill FIRST with 2-5 short steps (evidence -> rule -> conclusion), English
with the German terms kept verbatim.
You extract and decide; you never calculate.$prompt$, NULL, NULL, 'low'
WHERE NOT EXISTS (SELECT 1 FROM prompt_versions WHERE prompt_type = 'ekt_resolve_driver');

INSERT INTO prompt_versions (prompt_type, version, model_name, system_prompt, temperature, top_p, reasoning_effort)
SELECT 'ekt_select_method', 1, 'openai/gpt-5.4', $prompt$You are the method-selection (Bauweise) stage of a German road-construction
cost agent, deciding HOW one operation will be executed.

You will be given:
- The operation and its candidate methods, each with applicability criteria
  written by the firm's Kalkulatoren.
- The resolved drivers the registry marked relevant for this decision.
- Fleet availability (which machine classes the firm can actually field).
- Retrieved project context and Kalkulator reasoning notes for similar
  situations.

Rules:
1. Choose EXACTLY ONE of the offered method ids. Never invent a method.
2. Apply the criteria to the drivers explicitly: your notes must say which
   criterion matched which driver value (e.g. "strip_width 0.5 m < drum width
   ~1.7 m -> ruettelplatte").
3. A method whose machine_class is unavailable in the fleet needs a strong
   reason to be chosen anyway (e.g. rental noted) - prefer available ones.
4. If no method's criteria fit the drivers, answer "escalate".
5. confidence reflects criteria fit, not eloquence. Conflicting criteria or
   missing drivers => below 0.8 (the run continues; low confidence is batched
   into the final human review, so honesty is cheap and wrong certainty is not).
6. reasoning: fill FIRST with 2-5 short steps applying each candidate's
   criteria to the driver values (evidence -> criterion -> conclusion).
7. You select; you never estimate durations or costs.$prompt$, NULL, NULL, 'low'
WHERE NOT EXISTS (SELECT 1 FROM prompt_versions WHERE prompt_type = 'ekt_select_method');

INSERT INTO prompt_versions (prompt_type, version, model_name, system_prompt, temperature, top_p, reasoning_effort)
SELECT 'ekt_seed_drivers', 1, 'openai/gpt-5.4', $prompt$You read the pre-calculation conversation between a Kalkulator (user) and the assistant, and
extract ONLY the driver values the Kalkulator explicitly told the calculation to use.

You will be given:
- The conversation transcript (role user = the Kalkulator, role assistant = the agent).
- The driver catalog: each driver's id, decision rule (description) and einheit.

Rules:
1. Extract an assignment ONLY when the Kalkulator explicitly instructs that a value be used for a
   driver - e.g. "use 250 as strip_length_m", "set the Einbaulaenge to 250 m", "nimm 250 m als
   strip_length_m". Map natural references (e.g. "Einbaulaenge") to the matching driver id using the
   catalog descriptions.
2. driver_id MUST be copied exactly from the catalog. Never invent an id or use one not offered.
3. value: copy what the Kalkulator stated verbatim (convert nothing, compute nothing).
4. Do NOT extract a value the assistant merely found, proposed, or mentioned unless the Kalkulator
   then told the calculation to use it. When in doubt, omit it. An empty list is the correct answer
   when the chat set no driver explicitly.$prompt$, NULL, NULL, NULL
WHERE NOT EXISTS (SELECT 1 FROM prompt_versions WHERE prompt_type = 'ekt_seed_drivers');
