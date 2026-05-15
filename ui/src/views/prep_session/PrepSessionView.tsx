// Prep session view.
//
// Layout:
//   <SessionHeader>   — position, question count, eval trigger, exit button
//   <MessageList>     — full-width; no tool results in prep sessions
//   <ChatInput>       — locked to slash commands + answers only
//   <EvalDrawer>      — slide-in overlay; open state is local useState
//
// Data:
//   - Conversation header + messages from existing useConversation /
//     useConversationMessages hooks (PrepSessionConversation is a Conversation).
//   - Eval scores from useEvalScores (seeded on load; kept current by the
//     eval-stream subscription inside usePrepSessionConversation).

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useConversation, useConversationMessages } from '../../api/conversations';
import { useConversationList } from '../../api/conversations';
import { usePrepSessionConversation } from './hooks/usePrepSessionConversation';
import { SessionHeader } from './SessionHeader';
import { EvalDrawer } from './EvalDrawer';
import { MessageList } from '../../components/chat/MessageList';
import { ChatInput } from '../../components/chat/ChatInput';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { PREP_SESSION_SLASH_COMMANDS } from '../../lib/slash-commands';
import type { MessageDTO, PrepSessionConversationDTO } from '../../types/generated';

export function PrepSessionView() {
  const { conversationId } = useParams<{ conversationId: string }>();
  if (!conversationId) return <ErrorState message="Missing conversation id" />;
  return <PrepSessionViewInner sessionId={conversationId} />;
}

function PrepSessionViewInner({ sessionId }: { sessionId: string }) {
  const navigate = useNavigate();
  const conversationQuery = useConversation(sessionId);
  const messagesQuery = useConversationMessages(sessionId);
  const allConversations = useConversationList();

  // Find the workspace conversation id so submitCommand can navigate back.
  const workspaceConversationId = useMemo(
    () =>
      allConversations.data?.find((c) => c.type === 'workspace')?.id,
    [allConversations.data],
  );

  const {
    streamMessages,
    streamingMessageId,
    isStreaming,
    startInitialTurn,
    sendAnswer,
    submitCommand,
  } = usePrepSessionConversation(sessionId, workspaceConversationId);

  const [evalOpen, setEvalOpen] = useState(false);

  const session =
    conversationQuery.data?.type === 'prep_session'
      ? (conversationQuery.data as PrepSessionConversationDTO)
      : null;

  // Fire initial turn once when: session is loaded, in_progress, history empty.
  // Use a ref so a failed attempt doesn't re-trigger — if the stream errors
  // the messages list stays empty, which would otherwise loop forever.
  const initialTurnFiredRef = useRef(false);
  const messages = messagesQuery.data ?? [];

  useEffect(() => {
    if (
      !initialTurnFiredRef.current &&
      !messagesQuery.isLoading &&
      session?.status === 'in_progress' &&
      messages.length === 0 &&
      !isStreaming
    ) {
      initialTurnFiredRef.current = true;
      startInitialTurn();
    }
  // startInitialTurn is stable (useCallback with fixed deps).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.status, messages.length, messagesQuery.isLoading, isStreaming]);

  // Merge server messages with in-flight stream messages, server wins on id.
  const merged: MessageDTO[] = useMemo(() => {
    const byId = new Map<string, MessageDTO>();
    for (const m of messages) byId.set(m.id, m);
    for (const m of streamMessages) {
      if (!byId.has(m.id)) byId.set(m.id, m);
    }
    return [...byId.values()].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
  }, [messages, streamMessages]);

  const lastVisibleKind = [...merged]
    .reverse()
    .find((m) => m.kind !== 'function_call')?.kind;
  const isThinking =
    isStreaming &&
    (lastVisibleKind === 'candidate_message' || merged.length === 0);

  if (conversationQuery.isLoading || messagesQuery.isLoading) {
    return <LoadingState />;
  }
  if (conversationQuery.isError) {
    return (
      <ErrorState
        message={(conversationQuery.error as Error).message}
        onRetry={() => conversationQuery.refetch()}
      />
    );
  }
  if (!session) {
    return <ErrorState message="Not a prep session" />;
  }

  return (
    <div className="flex h-full flex-col">
      <SessionHeader
        session={session}
        onExit={() => submitCommand('/exit')}
        onBack={() =>
          workspaceConversationId
            ? navigate(`/c/${workspaceConversationId}`)
            : navigate('/')
        }
        onOpenEval={() => setEvalOpen(true)}
        isStreaming={isStreaming}
      />

      <MessageList
        messages={merged}
        streamingMessageId={streamingMessageId}
        isThinking={isThinking}
      />

      <ChatInput
        onSend={sendAnswer}
        onSlashCommand={(cmd) => submitCommand(cmd as '/exit')}
        slashCommands={PREP_SESSION_SLASH_COMMANDS}
        placeholder="Answer the question, or type /exit to cancel…"
        hint={
          session.status !== 'in_progress'
            ? `Session ${session.status}`
            : isStreaming
              ? 'Thinking…'
              : 'type /exit to cancel'
        }
        disabled={session.status !== 'in_progress' || isStreaming}
        draftKey={`session:${sessionId}`}
      />

      <EvalDrawer
        open={evalOpen}
        onClose={() => setEvalOpen(false)}
        sessionId={sessionId}
        dimensions={session.evaluator_dimensions}
        scaleMax={session.evaluator_scale_max}
      />
    </div>
  );
}
