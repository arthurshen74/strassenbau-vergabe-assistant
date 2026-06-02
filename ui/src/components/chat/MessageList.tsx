// Scrollable message list with auto-scroll-to-bottom that pauses when the
// user has scrolled away. We intentionally do NOT virtualize yet.
//
// Filtering: tool messages (function_call / function_call_output) are
// protocol-only and never rendered — tool output surfaces in the main window.

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { DisplayMessage } from './types';
import { Message } from './Message';
import { ThinkingIndicator } from '../feedback/ThinkingIndicator';

interface MessageListProps {
  messages: DisplayMessage[];
  /** id of a message currently being streamed (for caret/aria-busy). */
  streamingMessageId?: string | null;
  /**
   * When true, renders a prominent ThinkingIndicator after the last message —
   * used while the dispatcher LLM is processing but hasn't emitted any visible
   * output yet.
   */
  isThinking?: boolean;
  className?: string;
}

const STICK_TO_BOTTOM_PX = 100;

export function MessageList({
  messages,
  streamingMessageId,
  isThinking,
  className,
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [stick, setStick] = useState(true);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setStick(distance < STICK_TO_BOTTOM_PX);
  };

  useLayoutEffect(() => {
    if (!stick) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, stick]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  const visible = messages.filter(
    (m) => m.kind !== 'function_call' && m.kind !== 'function_call_output',
  );

  return (
    <div
      ref={scrollRef}
      onScroll={onScroll}
      className={'flex-1 overflow-y-auto px-6 py-4 ' + (className ?? '')}
    >
      <div className="flex max-w-xl sm:max-w-2xl md:max-w-4xl lg:max-w-6xl xl:max-w-7xl flex-col gap-3">
        {visible.map((m) => (
          <Message
            key={m.message_uuid}
            m={m}
            streaming={m.message_uuid === streamingMessageId}
          />
        ))}
        {isThinking && <ThinkingIndicator size="lg" label="Thinking" />}
      </div>
    </div>
  );
}
