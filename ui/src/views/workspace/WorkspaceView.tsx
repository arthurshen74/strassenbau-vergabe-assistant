// The project-chat view: the conversation fills the area above the chat input. Sidebar commands
// open the global main window at the shell level (it overlays this view), so this component only
// renders the thread.
//
// The display list is server messages + local stream messages, deduped by
// message_uuid (server wins) so placeholders fall away once the server
// reconciles after a turn completes.

import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useConversation, useConversationMessages } from '../../api/conversations';
import { useProject } from '../../api/projects';
import { useWorkspaceConversation } from './hooks/useWorkspaceConversation';
import { MessageList } from '../../components/chat/MessageList';
import { ChatInput } from '../../components/chat/ChatInput';
import { RetrievalConfigBar } from '../../components/chat/RetrievalConfigBar';
import { useRetrievalConfig } from '../../store/retrievalConfig';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import type { DisplayMessage } from '../../components/chat/types';

export function WorkspaceView() {
  const { conversationId } = useParams<{ conversationId: string }>();
  if (!conversationId) {
    return <ErrorState message="Missing conversation id" />;
  }
  return <WorkspaceViewInner conversationId={conversationId} />;
}

function WorkspaceViewInner({ conversationId }: { conversationId: string }) {
  const conversation = useConversation(conversationId);
  const projectUuid = conversation.data?.project_uuid ?? undefined;
  const project = useProject(projectUuid);
  const retrievalConfig = useRetrievalConfig(conversationId);
  const messagesQuery = useConversationMessages(conversationId);
  const { streamMessages, streamingMessageId, isStreaming, sendMessage } =
    useWorkspaceConversation(conversationId, retrievalConfig);

  const merged: DisplayMessage[] = useMemo(() => {
    const byId = new Map<string, DisplayMessage>();
    for (const m of messagesQuery.data ?? []) byId.set(m.message_uuid, m);
    for (const m of streamMessages) {
      if (!byId.has(m.message_uuid)) byId.set(m.message_uuid, m);
    }
    return [...byId.values()].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
  }, [messagesQuery.data, streamMessages]);

  // Show the ThinkingIndicator after the last user message while the
  // agent is processing but hasn't emitted visible output yet.
  const lastVisibleKind = [...merged]
    .reverse()
    .find(
      (m) =>
        m.kind !== 'function_call' &&
        !(m.kind === 'function_call_output' && !m.success),
    )?.kind;
  const isThinking = isStreaming && lastVisibleKind === 'user';

  if (conversation.isLoading) {
    return <LoadingState />;
  }
  if (conversation.isError) {
    return (
      <ErrorState
        message={(conversation.error as Error).message}
        onRetry={() => conversation.refetch()}
      />
    );
  }

  const title =
    project.data?.project_name ?? conversation.data?.title ?? 'Project chat';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center border-b border-zinc-950/5 px-4 dark:border-white/5">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{title}</div>
      </header>
      <MessageList
        messages={merged}
        streamingMessageId={streamingMessageId}
        isThinking={isThinking}
        projectUuid={projectUuid}
      />

      <RetrievalConfigBar conversationId={conversationId} />

      <ChatInput
        onSend={sendMessage}
        disabled={isStreaming}
        placeholder="Ask about this project…"
        draftKey={`ws:${conversationId}`}
        hint={isStreaming ? 'Thinking…' : undefined}
      />
    </div>
  );
}
