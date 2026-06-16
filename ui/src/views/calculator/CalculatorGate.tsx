// The pre-run gate of an ekt_calculator conversation. The Kalkulator discusses the position as an
// ordinary project chat (the same /turn handler) until they ask to run it. Asking trips the agent's
// start_calculation tool; once that turn completes we hand off to the live run via onStart.

import { useMemo, useRef } from 'react';

import { useConversationMessages } from '../../api/conversations';
import { ChatInput } from '../../components/chat/ChatInput';
import { MessageList } from '../../components/chat/MessageList';
import { useWorkspaceConversation } from '../workspace/hooks/useWorkspaceConversation';
import { mergeMessages } from './mergeMessages';

// The agent's control tool that signals "run the calculation now" (ProjectChatAgent).
const TOOL_START_CALCULATION = 'start_calculation';

export function CalculatorGate({
  conversationId,
  projectUuid,
  onStart,
}: {
  conversationId: string;
  projectUuid?: string;
  onStart: () => void;
}) {
  const messagesQuery = useConversationMessages(conversationId);
  const startRequestedRef = useRef(false);
  const { streamMessages, streamingMessageId, isStreaming, sendMessage } =
    useWorkspaceConversation(conversationId, undefined, (name) => {
      if (name === TOOL_START_CALCULATION) startRequestedRef.current = true;
    });

  // Run the turn as normal project chat; if the agent asked to start the calculation during it,
  // hand off once the turn (incl. its message refetch) has settled.
  const handleSend = (text: string) => {
    startRequestedRef.current = false;
    void (async () => {
      await sendMessage(text);
      if (startRequestedRef.current) onStart();
    })();
  };

  const merged = useMemo(
    () => mergeMessages(messagesQuery.data, streamMessages),
    [messagesQuery.data, streamMessages],
  );
  // Show the thinking indicator after the user's message until the agent emits visible output.
  const lastVisibleKind = [...merged]
    .reverse()
    .find((m) => m.kind !== 'function_call' && !(m.kind === 'function_call_output' && !m.success))
    ?.kind;

  return (
    <>
      <MessageList
        messages={merged}
        streamingMessageId={streamingMessageId}
        isThinking={isStreaming && lastVisibleKind === 'user'}
        projectUuid={projectUuid}
      />
      <ChatInput
        onSend={handleSend}
        disabled={isStreaming}
        placeholder="Antworten Sie, oder bitten Sie um die Kalkulation…"
        draftKey={`calc-gate:${conversationId}`}
        hint={isStreaming ? 'Thinking…' : undefined}
      />
    </>
  );
}
