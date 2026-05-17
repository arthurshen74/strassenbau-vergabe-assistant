/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export type IPAPrompt = "dispatcher" | "interviewer" | "evaluator" | "judge" | "utility";
export type ApiType = "openai_chat" | "anthropic_messages";

export interface AssistantMessageDTO {
  id: string;
  conversation_id: string;
  created_at: string;
  kind: "assistant_message";
  content: string;
}
/**
 * Sidebar entry. Carries enough to group/sort and render a status pill.
 */
export interface ConversationSummaryDTO {
  id: string;
  type: "workspace" | "prep_session" | "judge_run";
  title: string;
  updated_at: string;
  status?: string | null;
}
export interface DoneEvent {
  event: "done";
}
export interface ErrorEvent {
  event: "error";
  message: string;
  recoverable: boolean;
}
export interface EvalDimensionDTO {
  name: string;
  description: string;
  scale_min: number;
  scale_max: number;
}
export interface EvalScoreDTO {
  id: string;
  session_id: string;
  after_message_id: string;
  dimension: string;
  score: number | null;
  rationale: string | null;
  evaluator_prompt_id: string;
  evaluator_prompt_version: number;
  created_at: string;
}
export interface EvalUpdateEvent {
  event: "eval_update";
  dimension: string;
  score: number | null;
  rationale: string | null;
  after_message_id: string;
  after_message_created_at: string;
}
export interface FunctionCallEvent {
  event: "function_call";
  name: string;
  arguments: {
    [k: string]: unknown;
  };
  call_id: string;
}
export interface FunctionCallMessageDTO {
  id: string;
  conversation_id: string;
  created_at: string;
  kind: "function_call";
  name: string;
  arguments: {
    [k: string]: unknown;
  };
  call_id: string;
}
export interface FunctionCallOutputEvent {
  event: "function_call_output";
  call_id: string;
  tool_name?: string | null;
  success: boolean;
  data?: {
    [k: string]: unknown;
  } | null;
  errors?: string[] | null;
}
export interface FunctionCallOutputMessageDTO {
  id: string;
  conversation_id: string;
  created_at: string;
  kind: "function_call_output";
  call_id: string;
  tool_name?: string | null;
  success: boolean;
  data?: {
    [k: string]: unknown;
  } | null;
  errors?: string[] | null;
}
export interface InterviewerDeltaEvent {
  event: "interviewer_delta";
  content: string;
  question_number: number;
}
export interface JudgeFindingDTO {
  dimension: string;
  quality_score: number;
  examples: {
    [k: string]: unknown;
  }[];
  rationale: string;
}
export interface JudgeReportDTO {
  evaluator_prompt_id: string;
  evaluator_prompt_version: number;
  judge_prompt_id: string;
  judge_prompt_version: number;
  sessions_evaluated: string[];
  findings: JudgeFindingDTO[];
  summary: string;
}
export interface JudgeRunConversationDTO {
  type: "judge_run";
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  evaluator_prompt_id: string;
  evaluator_prompt_version: number;
  judge_prompt_id: string;
  judge_prompt_version: number;
  session_ids: string[];
  status: "pending" | "running" | "complete" | "failed";
  report?: JudgeReportDTO | null;
}
export interface PositionDTO {
  id: string;
  versions: PositionVersionDTO[];
  current_version: number;
  archived: boolean;
  created_at: string;
  updated_at: string;
}
export interface PositionVersionDTO {
  version: number;
  title: string;
  company: string;
  department: string;
  level: "junior" | "mid" | "senior" | "staff";
  salary_min: number | null;
  salary_max: number | null;
  remote: boolean;
  location: string | null;
  skills: SkillRequirementDTO[];
  description: string | null;
  notes: string | null;
  created_at: string;
}
export interface SkillRequirementDTO {
  skill: string;
  proficiency: "novice" | "practitioner" | "advanced" | "expert";
}
/**
 * Compact view for list responses; pulls fields from current_version.
 */
export interface PositionSummaryDTO {
  id: string;
  title: string;
  company: string;
  department: string;
  level: "junior" | "mid" | "senior" | "staff";
  current_version: number;
  archived: boolean;
  updated_at: string;
}
export interface PrepSessionConversationDTO {
  type: "prep_session";
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  position_id: string;
  position_version: number;
  evaluator_prompt_id: string;
  evaluator_prompt_version: number;
  interviewer_prompt_id: string;
  interviewer_prompt_version: number;
  status: "in_progress" | "complete";
  question_count: number;
  target_question_count: number;
  deleted: boolean;
  evaluator_dimensions: EvalDimension[];
  evaluator_scale_max: number;
}
export interface EvalDimension {
  name: string;
  description: string;
  scale_min?: number;
  scale_max?: number;
  [k: string]: unknown;
}
export interface ProfileDTO {
  id: string;
  name: string;
  years_experience: number;
  resume_text: string;
  updated_at: string;
}
export interface PromptDTO {
  id: string;
  prompt_type: IPAPrompt;
  name: string;
  version: number;
  api_type: ApiType;
  api_base_url: string;
  model_name: string;
  system_prompt: string;
  initial_assistant_message: string | null;
  temperature: number;
  top_p: number;
  min_p: number | null;
  dimensions: EvalDimensionDTO[] | null;
  archived: boolean;
  created_at: string;
}
/**
 * Compact view for list / picker responses.
 *
 * ``version`` here is the latest version of the group; ``archived``
 * reflects the group state.
 */
export interface PromptSummaryDTO {
  id: string;
  prompt_type: IPAPrompt;
  name: string;
  version: number;
  model_name: string;
  archived: boolean;
  created_at: string;
}
export interface SendMessageRequest {
  content: string;
}
export interface SlashCommandRequest {
  command: "/exit" | "/cancel" | "/rerun";
}
export interface TextDeltaEvent {
  event: "text_delta";
  content: string;
}
export interface UINoticeEvent {
  event: "ui_notice";
  content: string;
}
export interface UINoticeMessageDTO {
  id: string;
  conversation_id: string;
  created_at: string;
  kind: "ui_notice";
  content: string;
}
/**
 * Request body for ``PATCH /api/profile``.
 *
 * Mirrors the constraints on ``UpdateProfileArgs`` so the REST surface
 * enforces the same rules the LLM sees in the tool schema: every field
 * is individually optional, ``years_experience`` must be ``>= 0``, and
 * at least one field must be supplied (no-op updates are rejected at
 * validation time).
 */
export interface UpdateProfileRequest {
  name?: string | null;
  years_experience?: number | null;
  resume_text?: string | null;
}
export interface UserMessageDTO {
  id: string;
  conversation_id: string;
  created_at: string;
  kind: "user_message";
  content: string;
}
export interface WorkspaceConversationDTO {
  type: "workspace";
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
/**
 * Request body for ``POST /extract/position-info/text``.
 *
 * The user pasted a job description (e.g. copied from a webpage). We
 * cap the length client-side too, but enforce a sane upper bound here
 * so a runaway paste can't punish the LLM cost.
 */
export interface ExtractFromTextRequest {
  text: string;
}
/**
 * Output shape from ``POST /extract/position-info``.
 *
 * Same field set as :class:`PositionFieldsBody` but every field is
 * optional — the model returns whatever it could find. The frontend
 * form pre-fills from this and lets the user fill the gaps.
 */
export interface ExtractedPositionDTO {
  title?: string | null;
  company?: string | null;
  department?: string | null;
  level?: ("junior" | "mid" | "senior" | "staff") | null;
  salary_min?: number | null;
  salary_max?: number | null;
  remote?: boolean;
  location?: string | null;
  skills?: SkillRequirementBody[];
  description?: string | null;
  notes?: string | null;
}
export interface SkillRequirementBody {
  skill: string;
  proficiency: "novice" | "practitioner" | "advanced" | "expert";
}
/**
 * Partial-update fields used by ``PATCH /positions/{id}``.
 *
 * Every field optional individually but at least one must be supplied.
 * Mirrors :class:`ModifyPositionArgs` minus ``position_id`` (which
 * comes from the URL).
 */
export interface ModifyPositionBody {
  title?: string | null;
  company?: string | null;
  department?: string | null;
  level?: ("junior" | "mid" | "senior" | "staff") | null;
  salary_min?: number | null;
  salary_max?: number | null;
  remote?: boolean | null;
  location?: string | null;
  skills?: SkillRequirementBody[] | null;
  description?: string | null;
  notes?: string | null;
}
/**
 * Full position fields used by ``POST /positions``.
 */
export interface PositionFieldsBody {
  title: string;
  company: string;
  department: string;
  level: "junior" | "mid" | "senior" | "staff";
  salary_min?: number | null;
  salary_max?: number | null;
  remote?: boolean;
  location?: string | null;
  skills?: SkillRequirementBody[];
  description?: string | null;
  notes?: string | null;
}
/**
 * Partial-update body for ``POST /prompts/{prompt_type}/{name}/versions``.
 *
 * Mirrors the tool input schema; every field optional individually but
 * at least one must be supplied. Fields not set inherit from the
 * latest existing version.
 */
export interface EditPromptBody {
  api_type?: ApiType | null;
  api_base_url?: string | null;
  model_name?: string | null;
  system_prompt?: string | null;
  initial_assistant_message?: string | null;
  temperature?: number | null;
  top_p?: number | null;
  min_p?: number | null;
  dimensions?: EvalDimensionBody[] | null;
}
export interface EvalDimensionBody {
  name: string;
  description: string;
  scale_min?: number;
  scale_max?: number;
}
/**
 * All versions of one ``(prompt_type, name)`` plus latest detail.
 */
export interface PromptGroupDTO {
  prompt_type: IPAPrompt;
  name: string;
  archived: boolean;
  latest: PromptDTO;
  versions: PromptDTO[];
}
/**
 * One turn in a prompt-test transcript.
 *
 * We accept ``role`` as a free string for forward compatibility (the
 * OpenAI Chat Completions surface keeps adding roles), but the
 * expected values today are ``"user"`` and ``"assistant"``.
 */
export interface TestPromptMessage {
  role: string;
  content: string;
}
/**
 * Body for ``POST /prompts/{prompt_id}/test``.
 *
 * The full ``messages`` list is sent each call; the test panel keeps
 * the conversation in client state and replays it. We deliberately
 * don't persist test transcripts — they're ephemeral and would
 * confuse the dispatcher's view of conversation history if they
 * leaked into ``messages`` collection.
 */
export interface TestPromptRequest {
  /**
   * @minItems 1
   * @maxItems 50
   */
  messages: [TestPromptMessage, ...TestPromptMessage[]];
}

// ---- Types pinned by scripts/export_schema.py (pydantic2ts ordering) ----

export interface PromptExecutionLogSummaryDTO {
  id: string;
  prompt_type: IPAPrompt;
  prompt_name: string;
  prompt_version: number;
  model_name: string;
  tokens_in: number | null;
  tokens_out: number | null;
  duration_ms: number;
  sent_at: string;
  returned_at: string;
}

export interface PromptExecutionLogDetailDTO {
  id: string;
  prompt_type: IPAPrompt;
  prompt_name: string;
  prompt_version: number;
  provider_url: string;
  request_headers: Record<string, string>;
  model_name: string;
  temperature: number;
  top_p: number;
  min_p: number | null;
  system_prompt: string;
  tools: Record<string, unknown>[] | null;
  response_format: Record<string, unknown> | null;
  messages: Record<string, unknown>[];
  response_text: string | null;
  response_tool_calls: Record<string, unknown>[] | null;
  response_structured: Record<string, unknown> | unknown[] | null;
  finish_reason: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  duration_ms: number;
  sent_at: string;
  returned_at: string;
}

// ---- Discriminated unions (appended by scripts/export_schema.py) ----

export type MessageDTO =
  | UserMessageDTO
  | AssistantMessageDTO
  | FunctionCallMessageDTO
  | FunctionCallOutputMessageDTO
  | UINoticeMessageDTO;

export type ConversationDTO =
  | WorkspaceConversationDTO
  | PrepSessionConversationDTO
  | JudgeRunConversationDTO;

export type SSEEvent =
  | TextDeltaEvent
  | FunctionCallEvent
  | FunctionCallOutputEvent
  | EvalUpdateEvent
  | InterviewerDeltaEvent
  | UINoticeEvent
  | DoneEvent
  | ErrorEvent;
