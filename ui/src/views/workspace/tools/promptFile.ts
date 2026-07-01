// Parse a `.prompt` file into a PromptVersionCreate, mirroring the server-side
// seed loader (server/scripts/seed/prompts/__init__.py): a `---` YAML frontmatter
// fence carries the tunables (model_name, temperature, top_p), the body is the
// system prompt, and the prompt_type is derived from the filename stem. The
// frontmatter must not author prompt_type or system_prompt -- those are derived.

import type { PromptVersionCreate } from '../../../types/generated';

export const PROMPT_FILE_SUFFIX = '.prompt';
const FRONTMATTER_FENCE = '---';

const FRONTMATTER_KEY_MODEL_NAME = 'model_name';
const FRONTMATTER_KEY_TEMPERATURE = 'temperature';
const FRONTMATTER_KEY_TOP_P = 'top_p';
const FRONTMATTER_KEY_REASONING_EFFORT = 'reasoning_effort';

// Fields derived from the file itself, never set in frontmatter.
const DERIVED_KEYS = ['prompt_type', 'system_prompt'] as const;
const ALLOWED_KEYS = [
  FRONTMATTER_KEY_MODEL_NAME,
  FRONTMATTER_KEY_TEMPERATURE,
  FRONTMATTER_KEY_TOP_P,
  FRONTMATTER_KEY_REASONING_EFFORT,
] as const;

type PromptType = PromptVersionCreate['prompt_type'];

// The seedable prompt types (one .prompt file each). ekt_calculator is a conversation
// discriminator, not a seeded prompt, so it is intentionally excluded.
export const PROMPT_TYPES: readonly PromptType[] = [
  'dispatcher',
  'project_chat',
  'aggregate_lv_membership',
  'multi_question_generator',
  'lv_extraction',
  'conversation_name',
  'ekt_leistung_classify',
  'ekt_chat_values',
  'ekt_langtext_extract',
  'ekt_output_narrate',
  'project_context_resolve',
];

type Scalar = string | number | null;

export class PromptFileError extends Error {}

export function parsePromptFile(filename: string, text: string): PromptVersionCreate {
  if (!filename.endsWith(PROMPT_FILE_SUFFIX)) {
    throw new PromptFileError(`File must be a ${PROMPT_FILE_SUFFIX} file.`);
  }
  const stem = filename.slice(0, -PROMPT_FILE_SUFFIX.length);
  if (!PROMPT_TYPES.includes(stem as PromptType)) {
    throw new PromptFileError(
      `Filename '${stem}' is not a known prompt type. Name the file <prompt_type>${PROMPT_FILE_SUFFIX}.`,
    );
  }

  const { meta, body } = splitFrontmatter(text);
  if (body === '') {
    throw new PromptFileError('Empty system prompt body.');
  }
  for (const key of DERIVED_KEYS) {
    if (key in meta) {
      throw new PromptFileError(`'${key}' is derived from the file, not set in frontmatter.`);
    }
  }
  for (const key of Object.keys(meta)) {
    if (!ALLOWED_KEYS.includes(key as (typeof ALLOWED_KEYS)[number])) {
      throw new PromptFileError(`Unknown frontmatter key '${key}'.`);
    }
  }

  const modelName = meta[FRONTMATTER_KEY_MODEL_NAME];
  if (typeof modelName !== 'string' || modelName === '') {
    throw new PromptFileError(`Frontmatter '${FRONTMATTER_KEY_MODEL_NAME}' is required.`);
  }

  return {
    prompt_type: stem as PromptType,
    model_name: modelName,
    system_prompt: body,
    temperature: numberOrNull(meta, FRONTMATTER_KEY_TEMPERATURE),
    top_p: numberOrNull(meta, FRONTMATTER_KEY_TOP_P),
    reasoning_effort: stringOrNull(meta, FRONTMATTER_KEY_REASONING_EFFORT),
  };
}

function splitFrontmatter(text: string): { meta: Record<string, Scalar>; body: string } {
  const lines = text.split(/\r?\n/);
  if (lines[0]?.trim() !== FRONTMATTER_FENCE) {
    throw new PromptFileError(`Must open with a '${FRONTMATTER_FENCE}' frontmatter fence.`);
  }
  const end = lines.findIndex((line, i) => i > 0 && line.trim() === FRONTMATTER_FENCE);
  if (end === -1) {
    throw new PromptFileError(`Missing closing '${FRONTMATTER_FENCE}' frontmatter fence.`);
  }

  const meta: Record<string, Scalar> = {};
  for (const line of lines.slice(1, end)) {
    if (line.trim() === '') continue;
    const sep = line.indexOf(':');
    if (sep === -1) {
      throw new PromptFileError(`Malformed frontmatter line: '${line}'.`);
    }
    meta[line.slice(0, sep).trim()] = parseScalar(line.slice(sep + 1));
  }
  return { meta, body: lines.slice(end + 1).join('\n').trim() };
}

function parseScalar(raw: string): Scalar {
  const v = raw.trim();
  if (v === '' || v === 'null' || v === '~') return null;
  if (
    (v.startsWith('"') && v.endsWith('"')) ||
    (v.startsWith("'") && v.endsWith("'"))
  ) {
    return v.slice(1, -1);
  }
  if (/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(v)) return Number(v);
  return v;
}

function numberOrNull(meta: Record<string, Scalar>, key: string): number | null {
  const v = meta[key];
  if (v === undefined || v === null) return null;
  if (typeof v === 'number') return v;
  throw new PromptFileError(`Frontmatter '${key}' must be a number or null.`);
}

function stringOrNull(meta: Record<string, Scalar>, key: string): string | null {
  const v = meta[key];
  if (v === undefined || v === null) return null;
  if (typeof v === 'string') return v;
  throw new PromptFileError(`Frontmatter '${key}' must be a string or null.`);
}
