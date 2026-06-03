// Single-shot dispatcher command bar in the sidebar: type a request, press Enter, and the
// dispatcher routes it to a view in the global main window. No conversation is created.

import { useState } from 'react';
import { useDispatchCommand } from './useDispatchCommand';

export function DispatchBar() {
  const { dispatch, isDispatching } = useDispatchCommand();
  const [text, setText] = useState('');

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || isDispatching) return;
    setText('');
    void dispatch(trimmed);
  };

  return (
    <form onSubmit={submit}>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={isDispatching}
        placeholder="Ask the assistant…"
        aria-label="Dispatcher command"
        className="w-full rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-blue-400 focus:outline-none disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      />
    </form>
  );
}
