// Inline test panel for a specific prompt version. The user types a
// message; the panel streams the assistant response back, then keeps
// the transcript so they can do follow-ups. Reset clears it.
//
// Local-only: nothing in here hits the messages collection. Test runs
// don't appear in the dispatcher's view of conversation history.
//
// We don't reuse <ChatInput>/<MessageList> from the workspace chat —
// those are tied to MessageDTO and SSE event types we don't want to
// pollute with test-specific concerns. The transcript model here is a
// trimmed-down `TestPromptMessage[]` that matches the backend body
// exactly.

import { useRef, useState } from 'react';
import { streamPromptTest } from '../../../api/prompts';
import { Button } from '../../../components/ui/button';
import { Heading } from '../../../components/ui/heading';
import { Badge } from '../../../components/ui/badge';
import { ThinkingIndicator } from '../../../components/feedback/ThinkingIndicator';
import type {
  PromptDTO,
  TestPromptMessage,
} from '../../../types/generated';

export interface PromptTesterProps {
  /** The version to test. Versions other than `latest` work too. */
  version: PromptDTO;
}

export function PromptTester({ version }: PromptTesterProps) {
  const [messages, setMessages] = useState<TestPromptMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  // Index of the assistant message currently being streamed, so deltas
  // append to the right slot. Cleared on `done`.
  const streamingIdxRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    // Append the user turn AND a placeholder assistant turn in one
    // setState; we'll fill the assistant content in via deltas.
    let assistantIdx = -1;
    setMessages((prev) => {
      const next: TestPromptMessage[] = [
        ...prev,
        { role: 'user', content: text },
        { role: 'assistant', content: '' },
      ];
      assistantIdx = next.length - 1;
      streamingIdxRef.current = assistantIdx;
      return next;
    });
    setInput('');
    setStreaming(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    // Build the transcript we'll send. The state update is async so we
    // recompute from messages + the just-added user turn.
    const transcript: TestPromptMessage[] = [
      ...messages,
      { role: 'user', content: text },
    ];

    try {
      await streamPromptTest(version.id, transcript, (event) => {
        if (event.event === 'text_delta') {
          setMessages((prev) => {
            const idx = streamingIdxRef.current;
            if (idx == null) return prev;
            return prev.map((m, i) =>
              i === idx ? { ...m, content: m.content + event.content } : m,
            );
          });
        } else if (event.event === 'error') {
          setMessages((prev) => {
            const idx = streamingIdxRef.current;
            if (idx == null) return prev;
            return prev.map((m, i) =>
              i === idx
                ? {
                    ...m,
                    content:
                      (m.content ? m.content + '\n\n' : '') +
                      `[error: ${event.message}]`,
                  }
                : m,
            );
          });
        }
      }, ctrl.signal);
    } catch (err) {
      // Network blew up; surface inline rather than throwing to the boundary.
      const msg = (err as Error).message ?? 'Stream failed';
      setMessages((prev) => {
        const idx = streamingIdxRef.current;
        if (idx == null) return prev;
        return prev.map((m, i) =>
          i === idx ? { ...m, content: `[stream failed: ${msg}]` } : m,
        );
      });
    } finally {
      setStreaming(false);
      streamingIdxRef.current = null;
      abortRef.current = null;
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const reset = () => {
    abortRef.current?.abort();
    setMessages([]);
    setInput('');
    setStreaming(false);
    streamingIdxRef.current = null;
  };

  return (
    <div className="flex flex-col gap-3 rounded-md border border-zinc-950/10 bg-zinc-50/50 p-3 dark:border-white/10 dark:bg-zinc-950/40">
      <div className="flex items-center justify-between gap-2">
        <Heading level={4}>Test prompt</Heading>
        <div className="flex items-center gap-1">
          <Badge color="zinc">v{version.version}</Badge>
          <Badge color="zinc">{version.model_name}</Badge>
        </div>
      </div>

      {messages.length === 0 ? (
        <div className="text-xs text-zinc-500">
          Send a message to see how this prompt responds. Multi-turn is
          supported — type a follow-up to continue the test conversation.
        </div>
      ) : (
        <div className="flex max-h-80 flex-col gap-2 overflow-y-auto">
          {messages.map((m, i) => {
            // While waiting for the first token of an assistant turn,
            // replace the empty placeholder bubble with the prominent
            // ThinkingIndicator instead of a bare ellipsis.
            //
            // We intentionally do NOT use streamingIdxRef.current here:
            // that ref is set inside a setMessages updater (a React
            // anti-pattern for side-effects) and may be null on the
            // first concurrent render with streaming=true. The safe
            // invariant is that there is always exactly one assistant
            // message with empty content during a streaming turn.
            const isStreamingPlaceholder =
              streaming &&
              m.role === 'assistant' &&
              !m.content;

            if (isStreamingPlaceholder) {
              return (
                <div key={i} className="flex justify-start">
                  <ThinkingIndicator size="lg" label="Thinking" />
                </div>
              );
            }

            return (
              <div
                key={i}
                className={
                  m.role === 'user'
                    ? 'flex justify-end'
                    : 'flex justify-start'
                }
              >
                <div
                  className={
                    m.role === 'user'
                      ? 'max-w-2xl rounded-2xl bg-zinc-200 px-3 py-1.5 text-sm whitespace-pre-wrap text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100'
                      : 'max-w-2xl text-sm whitespace-pre-wrap text-zinc-900 dark:text-zinc-100'
                  }
                >
                  {m.content}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Send a test message…"
          disabled={streaming}
          className="flex-1 resize-none rounded-md border border-zinc-950/10 bg-white px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-100"
        />
        <Button onClick={send} disabled={streaming || !input.trim()}>
          {streaming ? '…' : 'Send'}
        </Button>
        {messages.length > 0 && !streaming && (
          <Button plain onClick={reset}>
            Reset
          </Button>
        )}
      </div>
    </div>
  );
}
