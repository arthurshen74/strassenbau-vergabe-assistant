// The live run phase of an ekt_calculator conversation: streams the graph, parks a HITL interrupt
// for the Kalkulator, and offers an explicit re-open for a run left stalled by a mid-segment reload.
// Mounted by CalculatorConversationView once the gate hands off (autoStart), or when reopening a run
// that is already past the gate.

import { useEffect, useMemo, useRef } from 'react';

import { useConversation, useConversationMessages } from '../../api/conversations';
import { MessageList } from '../../components/chat/MessageList';
import { Button } from '../../components/ui/button';
import type { ConversationRead, MessageRead } from '../../types/generated';
import { InterruptPanel } from './InterruptPanel';
import { mergeMessages } from './mergeMessages';
import { useCalculatorConversation, type PendingInterrupt } from './useCalculatorConversation';

// The synthetic tool_name the run service persists an interrupt prompt under (see run_service.py).
const TOOL_INTERRUPT = 'interrupt';

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

export function CalculatorRun({
  conversationId,
  projectUuid,
  autoStart,
}: {
  conversationId: string;
  projectUuid?: string;
  autoStart: boolean;
}) {
  const conversation = useConversation(conversationId);
  const messagesQuery = useConversationMessages(conversationId);
  const { streamMessages, pendingInterrupt, isStreaming, startStream, resume } =
    useCalculatorConversation(conversationId);

  const status = conversation.data?.calculation_status;
  const messagesLoaded = messagesQuery.isSuccess;
  const noMessages = (messagesQuery.data?.length ?? 0) === 0;

  // Fire the run exactly once when arriving fresh from the gate hand-off. A reload past the gate
  // (autoStart false) is NOT auto-restarted; it offers an explicit Resume instead. The ref guard
  // survives StrictMode's double-invoke, so we deliberately do not abort on cleanup.
  const firedRef = useRef(false);
  useEffect(() => {
    if (firedRef.current || !autoStart) return;
    firedRef.current = true;
    void startStream();
  }, [autoStart, startStream]);

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

  return (
    <>
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
    </>
  );
}
