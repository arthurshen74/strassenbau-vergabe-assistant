// Scrollable message list with auto-scroll-to-bottom that pauses when the
// user has scrolled away. We intentionally do NOT virtualize yet.
//
// Filtering: function_call is protocol-only and never rendered. function_call_output
// is kept — project-chat tools render inline (Message decides; the dispatcher's render
// nothing). A get_context result feeds the following assistant answer's citations panel.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ContextChunk } from '../../types/generated';
import type { DisplayMessage } from './types';
import { Message } from './Message';
import {
  TOOL_GET_LV_CONTEXT,
  TOOL_GET_PROJECT_CONTEXT,
} from './messages/ToolResultMessage';
import type { CitationData } from './messages/CitationsPanel';

// The two retrieval tools whose results feed the answer's citations panel.
const CONTEXT_TOOLS: string[] = [TOOL_GET_PROJECT_CONTEXT, TOOL_GET_LV_CONTEXT];
import { ThinkingIndicator } from '../feedback/ThinkingIndicator';
import { toolActivityLabel, type AgentActivityStep } from './agentActivity';

// Marker on a persisted assistant message's `data` flagging it as the calculator's reasoning trail
// (run_service.CALC_REASONING_MARKER); such a message renders collapsed to its latest line.
const CALC_REASONING_MARKER = 'calc_reasoning';

function isReasoningMessage(m: DisplayMessage): boolean {
  return (
    m.kind === 'assistant' &&
    !!m.data &&
    (m.data as Record<string, unknown>)[CALC_REASONING_MARKER] === true
  );
}

function asArray<T>(value: unknown): T[] | null {
  return Array.isArray(value) ? (value as T[]) : null;
}

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
  /** The streaming turn's tool calls so far, rendered as the indicator's activity trail. */
  activity?: AgentActivityStep[];
  /** Project scope, for project-chat tool results that fetch page thumbnails. */
  projectUuid?: string;
  /** Collapse the currently-streaming assistant message as calculator reasoning (latest line). */
  collapseStreamingReasoning?: boolean;
  className?: string;
}

const STICK_TO_BOTTOM_PX = 100;

export function MessageList({
  messages,
  streamingMessageId,
  isThinking,
  activity,
  projectUuid,
  collapseStreamingReasoning,
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
  }, [messages, activity, isThinking, stick]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  const visible = messages.filter((m) => m.kind !== 'function_call');

  // A turn's context tool result(s) feed the next assistant answer's citations panel, merged so the
  // answer's [n] citations resolve across multiple retrieve calls (project + LV context).
  const citationByAssistant = useMemo(() => {
    const map = new Map<string, CitationData>();
    let context: ContextChunk[] = [];
    for (const m of visible) {
      if (
        m.kind === 'function_call_output' &&
        m.tool_name != null &&
        CONTEXT_TOOLS.includes(m.tool_name)
      ) {
        const c = asArray<ContextChunk>(m.data?.context);
        if (c) context = context.concat(c);
      } else if (m.kind === 'assistant' && context.length) {
        map.set(m.message_uuid, { context });
        context = [];
      }
    }
    return map;
  }, [visible]);

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
            citationData={citationByAssistant.get(m.message_uuid)}
            projectUuid={projectUuid}
            collapsibleReasoning={
              (collapseStreamingReasoning && m.message_uuid === streamingMessageId) ||
              isReasoningMessage(m)
            }
          />
        ))}
        {isThinking && (
          <ThinkingIndicator
            size="lg"
            label="Thinking"
            steps={activity?.map((s) => ({
              key: s.callId,
              label: toolActivityLabel(s),
              done: s.done,
            }))}
          />
        )}
      </div>
    </div>
  );
}
