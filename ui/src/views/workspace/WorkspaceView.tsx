// The dispatcher chat view. The conversation fills the area above the chat
// input; when a tool result or sidebar command opens the main window, it
// replaces the message list (the input stays pinned so the conversation
// continues). Closing the window returns the conversation to full height.
//
// The display list is server messages + local stream messages, deduped by
// message_uuid (server wins) so placeholders fall away once the server
// reconciles after a turn completes.

import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import {
  useConversation,
  useConversationMessages,
} from '../../api/conversations';
import { useWorkspaceConversation } from './hooks/useWorkspaceConversation';
import { MessageList } from '../../components/chat/MessageList';
import { ChatInput } from '../../components/chat/ChatInput';
import { MainWindow } from '../../components/mainwindow/MainWindow';
import { useMainWindowStore } from '../../store/mainWindow';
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
  const messagesQuery = useConversationMessages(conversationId);
  const { streamMessages, streamingMessageId, isStreaming, sendMessage } =
    useWorkspaceConversation(conversationId);
  const mainView = useMainWindowStore((s) => s.view);

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
  // dispatcher is processing but hasn't emitted visible output yet.
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

  const title = conversation.data?.title ?? 'Dispatcher';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex min-h-0 flex-1 flex-col">
        {mainView ? (
          <MainWindow view={mainView} />
        ) : (
          <>
            <header className="flex h-12 shrink-0 items-center border-b border-zinc-950/5 px-4 dark:border-white/5">
              <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {title}
              </div>
            </header>
            <MessageList
              messages={merged}
              streamingMessageId={streamingMessageId}
              isThinking={isThinking}
            />
          </>
        )}
      </div>

      <ChatInput
        onSend={sendMessage}
        disabled={isStreaming}
        placeholder="Ask the dispatcher…"
        draftKey={`ws:${conversationId}`}
        hint={isStreaming ? 'Thinking…' : undefined}
      />
    </div>
  );
}
