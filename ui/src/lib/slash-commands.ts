// Slash command parsing helpers. Used in two places:
//
// - Workspace chat: catalog comes from the backend (see api/dispatcher.ts).
//   The user's literal slash text is sent to the dispatcher, which
//   expands it server-side. ChatInput shows autocomplete suggestions
//   from the catalog but does NOT intercept submission — slash messages
//   travel through `onSend` like any other user message.
//
// - Prep session / judge run views: small, fixed slash sets that DO
//   short-circuit the LLM (`/exit`, `/cancel`, `/rerun`).
//   These views pass `onSlashCommand` so submission is intercepted and
//   forwarded to the appropriate REST endpoint instead of the chat
//   message stream.
//
// To support both shapes without two diverging APIs, the slash command
// type carries an optional description for the autocomplete UI. The
// fixed-set views build entries by hand; the workspace builds them
// from the API response.

export interface SlashCommandSpec {
  name: string;
  description?: string;
}

/** Fixed-set commands for prep session / judge run views. */
export const PREP_SESSION_SLASH_COMMANDS: SlashCommandSpec[] = [
  { name: '/exit', description: 'Cancel the session (destructive — cannot be undone)' },
];

export const JUDGE_RUN_SLASH_COMMANDS: SlashCommandSpec[] = [
  { name: '/cancel', description: 'Cancel the current judge run' },
  { name: '/rerun', description: 'Re-run with the same configuration' },
];

/**
 * If the trimmed input matches one of the supplied commands exactly,
 * return its name. Used by the judge_run interceptor path. Workspace
 * doesn't call this — it lets the literal text fall through.
 */
export function parseSlashCommand(
  input: string,
  allowed: SlashCommandSpec[],
): string | null {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) return null;
  const head = trimmed.split(/\s+/, 1)[0];
  return allowed.some((c) => c.name === head) ? head : null;
}

/**
 * Names that start with the user's current `/...` prefix. Used by the
 * autocomplete dropdown. Empty array when the input doesn't start with
 * a slash.
 */
export function matchingCommands(
  input: string,
  allowed: SlashCommandSpec[],
): SlashCommandSpec[] {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) return [];
  // Match by command head only; trailing context after a space is
  // fine and shouldn't suppress suggestions for the head.
  const head = trimmed.split(/\s+/, 1)[0];
  return allowed.filter((c) => c.name.startsWith(head));
}
