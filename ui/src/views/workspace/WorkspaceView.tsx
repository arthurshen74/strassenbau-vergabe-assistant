// The dispatcher-driven CRUD view. Users spend most of their time here.
//
// Composition:
//   - useConversation: fetches the workspace conversation header
//   - useConversationMessages: server-persisted message history
//   - useWorkspaceConversation: layered ephemeral stream state
//
// The display message list is server messages + local stream messages,
// deduped by id (server wins). This way once the server reconciles
// IDs after the stream completes, the placeholders silently fall away.

import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import {
  useConversation,
  useConversationMessages,
} from '../../api/conversations';
import { useWorkspaceConversation } from './hooks/useWorkspaceConversation';
import { MessageList } from '../../components/chat/MessageList';
import { ChatInput } from '../../components/chat/ChatInput';
import { useSlashCommands } from '../../api/dispatcher';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { ToolResultRouter } from './tools/ToolResultRouter';
import type { MessageDTO } from '../../types/generated';

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
  const {
    streamMessages,
    streamingMessageId,
    isStreaming,
    sendMessage,
  } = useWorkspaceConversation(conversationId);

  // Workspace slash commands are catalog-driven and expand server-side.
  // We pass them to ChatInput for autocomplete but do NOT pass
  // ``onSlashCommand`` — the literal text falls through to ``sendMessage``
  // and the dispatcher does the expansion.
  const slashCommands = useSlashCommands();

  const merged: MessageDTO[] = useMemo(() => {
    const byId = new Map<string, MessageDTO>();
    // server first
    for (const m of messagesQuery.data ?? []) byId.set(m.id, m);
    // local stream messages: keep only ones whose id isn't already on the server.
    for (const m of streamMessages) {
      if (!byId.has(m.id)) byId.set(m.id, m);
    }
    return [...byId.values()].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
  }, [messagesQuery.data, streamMessages]);

  // Show the ThinkingIndicator after the last user message while the
  // dispatcher LLM is processing but hasn't emitted any visible output
  // yet. We mirror MessageList's filter rules (drop function_call and
  // failed function_call_output) so a hidden function_call event that
  // arrives before the tool result doesn't prematurely hide the indicator.
  const lastVisibleKind = [...merged]
    .reverse()
    .find(
      (m) =>
        m.kind !== 'function_call' &&
        !(m.kind === 'function_call_output' && !m.success),
    )?.kind;
  const isThinking = isStreaming && lastVisibleKind === 'user_message';

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

  const title = conversation.data?.title ?? 'Workspace';

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center border-b border-zinc-950/5 px-4 dark:border-white/5">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {title}
        </div>
      </header>

      <MessageList
        messages={merged}
        streamingMessageId={streamingMessageId}
        isThinking={isThinking}
        renderToolResult={(m) => (
          <ToolResultRouter
            msg={m}
            // Only wire the callback when idle — prevents the user from
            // kicking off a second dispatcher turn mid-stream.
            onSendMessage={isStreaming ? undefined : sendMessage}
          />
        )}
      />

      <ChatInput
        onSend={sendMessage}
        disabled={isStreaming}
        placeholder="Ask the dispatcher or type / for shortcuts."
        draftKey={`ws:${conversationId}`}
        hint={isStreaming ? 'Thinking…' : undefined}
        slashCommands={slashCommands}
      />
    </div>
  );
}
