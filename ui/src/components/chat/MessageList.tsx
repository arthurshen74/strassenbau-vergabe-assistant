// Scrollable message list with auto-scroll-to-bottom that pauses when
// the user has scrolled away. We intentionally do NOT virtualize yet —
// turn that on (TanStack Virtual) once we have real conversation lengths
// to measure against. Premature virtualization makes streaming layout
// jitter much harder to reason about.
//
// Filtering rules (per FRONTEND.md §4):
//   - function_call messages are protocol noise — never rendered.
//   - failed function_call_output messages are silenced; the LLM
//     follows up with a clarifying assistant_message instead.

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type {
  FunctionCallOutputMessageDTO,
  MessageDTO,
} from '../../types/generated';
import { Message } from './Message';
import { ThinkingIndicator } from '../feedback/ThinkingIndicator';

interface MessageListProps {
  messages: MessageDTO[];
  /** id of a message currently being streamed (for caret/aria-busy). */
  streamingMessageId?: string | null;
  /**
   * When true, renders a prominent ThinkingIndicator after the last
   * message — used while the dispatcher LLM is processing but hasn't
   * emitted any visible output yet.
   */
  isThinking?: boolean;
  renderToolResult?: (msg: FunctionCallOutputMessageDTO) => React.ReactNode;
  className?: string;
}

const STICK_TO_BOTTOM_PX = 100;

export function MessageList({
  messages,
  streamingMessageId,
  isThinking,
  renderToolResult,
  className,
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [stick, setStick] = useState(true);

  // Track whether the user is "near bottom"; if so we keep auto-scrolling
  // on new messages, otherwise we leave their scroll position alone.
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

  // On first mount, snap to bottom regardless of stick.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  const visible = messages.filter((m) => {
    if (m.kind === 'function_call') return false;
    if (m.kind === 'function_call_output' && !m.success) return false;
    return true;
  });

  return (
    <div
      ref={scrollRef}
      onScroll={onScroll}
      className={'flex-1 overflow-y-auto px-6 py-4 ' + (className ?? '')}
    >
      <div className="flex max-w-xl sm:max-w-2xl md:max-w-4xl lg:max-w-6xl xl:max-w-7xl flex-col gap-3">
        {visible.map((m) => (
          <Message
            key={m.id}
            m={m}
            streaming={m.id === streamingMessageId}
            renderToolResult={renderToolResult}
          />
        ))}
        {isThinking && (
          <ThinkingIndicator
            size="lg"
            label="Thinking"
          />
        )}
      </div>
    </div>
  );
}
