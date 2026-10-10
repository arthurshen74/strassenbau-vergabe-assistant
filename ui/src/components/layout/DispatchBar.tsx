// Single-shot dispatcher command bar: type a request, press Enter, and the dispatcher routes it to
// a view in the global main window. No conversation is created.
//
// Typing "/" surfaces an autocomplete list of slash commands. A slash command pre-empts the LLM
// dispatcher entirely: it maps directly to a main-window view and opens it client-side (no data —
// the view body fetches via REST, same as the sidebar Command buttons).

import { useState } from 'react';
import { useDispatchCommand } from './useDispatchCommand';
import { useMainWindowStore, type MainWindowKind } from '../../store/mainWindow';
import {
  matchingCommands,
  parseSlashCommand,
  type SlashCommandSpec,
} from '../../lib/slash-commands';

interface DispatchSlashCommand extends SlashCommandSpec {
  kind: MainWindowKind;
}

const DISPATCH_SLASH_COMMANDS: DispatchSlashCommand[] = [
  { name: '/projects', description: 'View Projects', kind: 'projects' },
  { name: '/prompts', description: 'View Prompts', kind: 'prompts' },
  { name: '/ragqueries', description: 'View RAG Queries', kind: 'rag_queries' },
  { name: '/ingestlog', description: 'View Ingest Console', kind: 'ingest_console' },
  { name: '/execlog', description: 'View Prompt Execution Log', kind: 'prompt_execution_log' },
  { name: '/usagelog', description: 'View Usage Log', kind: 'prompt_usage_log' },
];

export function DispatchBar() {
  const { dispatch, isDispatching, message, clearMessage } = useDispatchCommand();
  const openMainWindow = useMainWindowStore((s) => s.openMainWindow);
  const [text, setText] = useState('');

  const onChange = (value: string) => {
    setText(value);
    if (message) clearMessage();
  };

  const runSlashCommand = (cmd: DispatchSlashCommand) => {
    setText('');
    clearMessage();
    openMainWindow({ kind: cmd.kind });
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || isDispatching) return;

    const name = parseSlashCommand(trimmed, DISPATCH_SLASH_COMMANDS);
    const cmd = DISPATCH_SLASH_COMMANDS.find((c) => c.name === name);
    if (cmd) {
      runSlashCommand(cmd);
      return;
    }

    setText('');
    void dispatch(trimmed);
  };

  const suggestions = text.startsWith('/')
    ? matchingCommands(text, DISPATCH_SLASH_COMMANDS)
    : [];

  return (
    <form onSubmit={submit} className="relative">
      {suggestions.length > 0 && (
        <div className="absolute top-full left-0 right-0 z-10 mt-1 flex flex-col gap-0.5 rounded-md border border-zinc-200 bg-white p-1 shadow-md dark:border-zinc-700 dark:bg-zinc-900">
          {suggestions.map((s) => (
            <button
              key={s.name}
              type="button"
              onClick={() => runSlashCommand(s)}
              className="flex items-baseline justify-between gap-3 rounded px-2 py-1 text-left text-xs hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              <span className="font-mono text-zinc-900 dark:text-zinc-100">{s.name}</span>
              {s.description && (
                <span className="truncate text-zinc-500 dark:text-zinc-400">{s.description}</span>
              )}
            </button>
          ))}
        </div>
      )}
      <input
        value={text}
        onChange={(e) => onChange(e.target.value)}
        disabled={isDispatching}
        placeholder="Ask the assistant…  (/ for commands)"
        aria-label="Dispatcher command"
        className="w-full rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-400 focus:outline-none disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      />
      {message && (
        <p className="mt-2 text-left text-xs text-zinc-500 dark:text-zinc-400">{message}</p>
      )}
    </form>
  );
}
