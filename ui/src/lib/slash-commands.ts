// Slash command parsing helpers, shared by every input that supports slash
// commands:
//
// - Dispatcher command bar: a slash command maps to a main-window view and is
//   handled entirely client-side, pre-empting the LLM dispatcher call.
// - Project chat: `/clear`, `/close`, `/remove` short-circuit the LLM and run
//   client-side conversation actions.
//
// Each input owns its own command list and decides what a matched command
// does; these helpers only parse and match. SlashCommandSpec carries an
// optional description for the autocomplete dropdown.

export interface SlashCommandSpec {
  name: string;
  description?: string;
}

/**
 * If the trimmed input's first token matches one of the supplied commands
 * exactly, return its name; otherwise null. Used to decide whether a
 * submission is a slash command or ordinary text.
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
 * Commands whose name starts with the user's current `/...` prefix. Drives the
 * autocomplete dropdown. Empty array when the input doesn't start with a slash.
 * Generic so callers keep their concrete command type (and any extra fields).
 */
export function matchingCommands<T extends SlashCommandSpec>(
  input: string,
  allowed: T[],
): T[] {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) return [];
  // Match by command head only; trailing context after a space is
  // fine and shouldn't suppress suggestions for the head.
  const head = trimmed.split(/\s+/, 1)[0];
  return allowed.filter((c) => c.name.startsWith(head));
}
