// Multi-line auto-growing chat input. Enter sends, Shift+Enter inserts a
// newline. Slash command parsing is delegated to lib/slash-commands —
// the input never inlines command logic.
//
// Drafts: when `draftKey` is provided we mirror the textarea into the
// drafts store so navigation away/back preserves what was typed. Server
// state never goes through this store.

import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { Button } from '../ui/button';
import { useDraftsStore } from '../../store/drafts';
import {
  matchingCommands,
  parseSlashCommand,
  type SlashCommandSpec,
} from '../../lib/slash-commands';

interface ChatInputProps {
  onSend: (text: string) => void;
  /**
   * If supplied, ChatInput intercepts a submitted slash command (exact
   * match against ``slashCommands``) and routes it to this handler
   * INSTEAD of ``onSend``. Used by views that need to short-circuit the
   * LLM. The workspace deliberately does NOT supply this — slash text
   * falls through to ``onSend`` and is expanded server-side by the
   * dispatcher.
   */
  onSlashCommand?: (cmd: string) => void;
  placeholder?: string;
  slashCommands?: SlashCommandSpec[];
  disabled?: boolean;
  hint?: string;
  draftKey?: string;
}

const MAX_ROWS = 6;
const LINE_HEIGHT_PX = 22;

export function ChatInput({
  onSend,
  onSlashCommand,
  placeholder = 'Type a message…',
  slashCommands,
  disabled,
  hint,
  draftKey,
}: ChatInputProps) {
  const draft = useDraftsStore((s) => (draftKey ? s.drafts[draftKey] ?? '' : ''));
  const setDraft = useDraftsStore((s) => s.setDraft);
  const clearDraft = useDraftsStore((s) => s.clearDraft);

  const [localValue, setLocalValue] = useState('');
  const value = draftKey ? draft : localValue;

  const setValue = (v: string) => {
    if (draftKey) setDraft(draftKey, v);
    else setLocalValue(v);
  };

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // auto-grow the textarea up to MAX_ROWS lines.
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const max = MAX_ROWS * LINE_HEIGHT_PX + 16;
    ta.style.height = `${Math.min(ta.scrollHeight, max)}px`;
  }, [value]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    if (slashCommands && onSlashCommand) {
      const cmd = parseSlashCommand(trimmed, slashCommands);
      if (cmd) {
        onSlashCommand(cmd);
        setValue('');
        if (draftKey) clearDraft(draftKey);
        return;
      }
    }
    onSend(trimmed);
    setValue('');
    if (draftKey) clearDraft(draftKey);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  // Slash command suggestions for the autocomplete dropdown.
  const suggestions =
    slashCommands && value.startsWith('/')
      ? matchingCommands(value, slashCommands)
      : [];

  return (
    <div className="border-t border-zinc-950/5 bg-white px-4 py-3 dark:border-white/5 dark:bg-zinc-900">
      <div className="mx-auto flex max-w-4xl flex-col gap-2">
        {suggestions.length > 0 && (
          <div className="flex flex-col gap-0.5 rounded-md border border-zinc-950/5 bg-white p-1 shadow-sm dark:border-white/10 dark:bg-zinc-900">
            {suggestions.map((s) => (
              <button
                key={s.name}
                type="button"
                onClick={() => {
                  // Insert the command name; preserve any trailing
                  // context the user already typed past the head.
                  const tail = value.includes(' ')
                    ? value.slice(value.indexOf(' '))
                    : ' ';
                  setValue(s.name + tail);
                  textareaRef.current?.focus();
                }}
                className="flex items-baseline justify-between gap-3 rounded px-2 py-1 text-left text-xs hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <span className="font-mono text-zinc-900 dark:text-zinc-100">
                  {s.name}
                </span>
                {s.description && (
                  <span className="truncate text-zinc-500 dark:text-zinc-400">
                    {s.description}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className={clsx(
              'flex-1 resize-none rounded-md border border-zinc-950/10 bg-white px-3 py-2 text-sm shadow-sm',
              'focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500',
              'dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-100',
              disabled && 'cursor-not-allowed opacity-60',
            )}
            aria-label="Message"
          />
          <Button onClick={submit} disabled={disabled || !value.trim()}>
            Send
          </Button>
        </div>
        {hint && (
          <div className="text-xs text-zinc-500 dark:text-zinc-400">{hint}</div>
        )}
      </div>
    </div>
  );
}
