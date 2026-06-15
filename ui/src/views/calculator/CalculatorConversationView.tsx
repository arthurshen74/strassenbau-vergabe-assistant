// The live/interactive phase of an ekt_calculator conversation. Arriving fresh from "Run
// calculation" auto-opens the run stream; reopening a paused run reconstructs the interrupt control
// from the persisted prompt so the Kalkulator can resume. Once complete, ConversationRouter sends
// the conversation to the normal workspace view (transcript + follow-up questions).

import { useEffect, useMemo, useRef } from 'react';

import {
  useConversation,
  useConversationMessages,
} from '../../api/conversations';
import { MessageList } from '../../components/chat/MessageList';
import { Button } from '../../components/ui/button';
import { LoadingState } from '../../components/feedback/LoadingState';
import type { DisplayMessage } from '../../components/chat/types';
import type { ConversationRead, MessageRead } from '../../types/generated';
import { InterruptPanel } from './InterruptPanel';
import { useCalculatorConversation, type PendingInterrupt } from './useCalculatorConversation';

// The synthetic tool_name the run service persists an interrupt prompt under (see run_service.py).
const TOOL_INTERRUPT = 'interrupt';

function mergeMessages(
  persisted: MessageRead[] | undefined,
  stream: DisplayMessage[],
): DisplayMessage[] {
  const byId = new Map<string, DisplayMessage>();
  for (const m of persisted ?? []) byId.set(m.message_uuid, m);
  for (const m of stream) if (!byId.has(m.message_uuid)) byId.set(m.message_uuid, m);
  return [...byId.values()].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
}

// Rebuild the pending interrupt from the last persisted prompt when reopening a paused run.
function derivePendingInterrupt(
  conversation: ConversationRead | undefined,
  messages: MessageRead[] | undefined,
): PendingInterrupt | null {
  if (!conversation || conversation.calculation_status !== 'awaiting_input' || !messages) {
    return null;
  }
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.kind === 'function_call' && m.tool_name === TOOL_INTERRUPT && m.arguments) {
      const args = m.arguments as Record<string, unknown>;
      const stage = typeof args.stage === 'string' ? args.stage : '';
      return { stage, payload: args };
    }
  }
  return null;
}

export function CalculatorConversationView({ conversationId }: { conversationId: string }) {
  const conversation = useConversation(conversationId);
  const projectUuid = conversation.data?.project_uuid ?? undefined;
  const messagesQuery = useConversationMessages(conversationId);
  const { streamMessages, pendingInterrupt, isStreaming, startStream, resume } =
    useCalculatorConversation(conversationId);

  const status = conversation.data?.calculation_status;
  const messagesLoaded = messagesQuery.isSuccess;
  const noMessages = (messagesQuery.data?.length ?? 0) === 0;

  // Auto-open the stream for a fresh run (created but never streamed) on first entry — whether the
  // user arrived from "Run calculation" or via the sidebar. A run left "running" WITH messages (a
  // reload mid-segment) is not auto-restarted; it offers an explicit Resume instead.
  // Auto-open the stream once for a fresh run. The ref guard suffices under StrictMode (the fiber —
  // and so the ref — is preserved across the dev double-invoke), so we deliberately do NOT abort on
  // cleanup: that would kill the stream the instant isStreaming flips and re-runs this effect.
  const startedRef = useRef(false);
  useEffect(() => {
    if (startedRef.current || isStreaming) return;
    if (status === 'running' && messagesLoaded && noMessages) {
      startedRef.current = true;
      void startStream();
    }
  }, [status, messagesLoaded, noMessages, isStreaming, startStream]);

  const interrupt =
    pendingInterrupt ?? derivePendingInterrupt(conversation.data, messagesQuery.data);
  const merged = useMemo(
    () => mergeMessages(messagesQuery.data, streamMessages),
    [messagesQuery.data, streamMessages],
  );

  // A run left "running" WITH persisted messages and no live stream (a reload mid-segment) is
  // stalled; offer an explicit re-open (the graph continues from its last checkpoint).
  const canResumeStalled =
    status === 'running' && !isStreaming && !interrupt && messagesLoaded && !noMessages;

  if (conversation.isLoading) return <LoadingState />;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center border-b border-zinc-950/5 px-4 dark:border-white/5">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {conversation.data?.title ?? 'EKT calculation'}
        </div>
      </header>
      <MessageList
        messages={merged}
        isThinking={isStreaming && !interrupt && merged.length === 0}
        projectUuid={projectUuid}
      />
      {interrupt ? (
        <InterruptPanel interrupt={interrupt} onResume={resume} disabled={isStreaming} />
      ) : canResumeStalled ? (
        <div className="border-t border-zinc-950/5 px-6 py-4 dark:border-white/5">
          <Button onClick={() => void startStream()}>Resume calculation</Button>
        </div>
      ) : null}
    </div>
  );
}
