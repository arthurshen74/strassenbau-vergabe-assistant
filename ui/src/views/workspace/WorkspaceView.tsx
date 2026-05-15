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

import { useMemo, useState } from 'react';
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
import {
  PositionDraftPanel,
  type PositionDraftSource,
} from './components/PositionDraftPanel';
import { PastePositionDialog } from './components/PastePositionDialog';
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
    appendToolResult,
  } = useWorkspaceConversation(conversationId);

  // The active pasted-text draft being reviewed in the draft panel.
  // We key the panel by source identity so a new paste unmounts and
  // restarts cleanly.
  const [draftSource, setDraftSource] = useState<PositionDraftSource | null>(
    null,
  );
  const [pasteOpen, setPasteOpen] = useState(false);
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

      {draftSource && (
        <PositionDraftPanel
          source={draftSource}
          onDismiss={() => setDraftSource(null)}
          onCreated={(position) => {
            setDraftSource(null);
            // Render the saved position as if the dispatcher had
            // emitted ``add_position`` — same inline card, including
            // the Edit affordance. The synthetic message is local-only
            // so it doesn't pollute the dispatcher's view of the
            // conversation; on reload the user can re-fetch the card
            // by asking the dispatcher to view their positions.
            appendToolResult(
              'add_position',
              position as unknown as Record<string, unknown>,
            );
          }}
        />
      )}

      <ChatInput
        onSend={sendMessage}
        disabled={isStreaming}
        placeholder="Ask the dispatcher, type / for shortcuts, or paste a job description."
        draftKey={`ws:${conversationId}`}
        hint={isStreaming ? 'Thinking…' : undefined}
        slashCommands={slashCommands}
        onPasteText={() => setPasteOpen(true)}
      />

      <PastePositionDialog
        open={pasteOpen}
        onClose={() => setPasteOpen(false)}
        onExtract={(text) => {
          setPasteOpen(false);
          setDraftSource({ kind: 'text', text });
        }}
      />
    </div>
  );
}
