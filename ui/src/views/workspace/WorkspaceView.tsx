// The project-chat view: the conversation fills the area above the chat input. Sidebar commands
// open the global main window at the shell level (it overlays this view), so this component only
// renders the thread.
//
// The display list is server messages + local stream messages, deduped by
// message_uuid (server wins) so placeholders fall away once the server
// reconciles after a turn completes.

import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  useConversation,
  useConversationMessages,
  useDeleteConversation,
} from '../../api/conversations';
import { useProject } from '../../api/projects';
import { useStartProjectChat } from '../main/useStartProjectChat';
import { useStartKatalogChat } from '../main/useStartKatalogChat';
import {
  useWorkspaceConversation,
  type PendingInterrupt,
} from './hooks/useWorkspaceConversation';
import { InterruptPanel } from './InterruptPanel';
import { MessageList } from '../../components/chat/MessageList';
import { ChatInput } from '../../components/chat/ChatInput';
import { RetrievalConfigBar } from '../../components/chat/RetrievalConfigBar';
import { useRetrievalConfig } from '../../store/retrievalConfig';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import type { SlashCommandSpec } from '../../lib/slash-commands';
import type { ConversationRead, MessageRead } from '../../types/generated';
import type { DisplayMessage } from '../../components/chat/types';

// The synthetic tool_name the run service persists a HITL interrupt prompt under (run_service.py).
const TOOL_INTERRUPT = 'interrupt';

// Rebuild the pending interrupt from the last persisted prompt when reopening a paused calculation
// (no live stream is in flight, so the interrupt event won't replay).
function derivePendingInterrupt(
  conversation: ConversationRead | undefined,
  messages: MessageRead[] | undefined,
): PendingInterrupt | null {
  if (
    !conversation ||
    conversation.calculation_status !== 'awaiting_input' ||
    !messages
  ) {
    return null;
  }
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (
      m.kind === 'function_call' &&
      m.tool_name === TOOL_INTERRUPT &&
      m.arguments
    ) {
      const args = m.arguments as Record<string, unknown>;
      return {
        stage: typeof args.stage === 'string' ? args.stage : '',
        payload: args,
      };
    }
  }
  return null;
}

// Client-side slash commands for project chat (short-circuit the LLM via ChatInput.onSlashCommand).
const SLASH_CLEAR = '/clear';
const SLASH_CLOSE = '/close';
const SLASH_REMOVE = '/remove';
const PROJECT_CHAT_SLASH_COMMANDS: SlashCommandSpec[] = [
  { name: SLASH_CLEAR, description: 'Start a fresh chat for this project' },
  { name: SLASH_CLOSE, description: 'Back to the dispatcher home' },
  { name: SLASH_REMOVE, description: 'Delete this conversation' },
];

export function WorkspaceView() {
  const { conversationId } = useParams<{ conversationId: string }>();
  if (!conversationId) {
    return <ErrorState message="Missing conversation id" />;
  }
  // Key by conversation so per-conversation stream state (incl. retained notices) resets on switch.
  return (
    <WorkspaceViewInner
      key={conversationId}
      conversationId={conversationId}
    />
  );
}

function WorkspaceViewInner({ conversationId }: { conversationId: string }) {
  const navigate = useNavigate();
  const startProjectChat = useStartProjectChat();
  const startKatalogChat = useStartKatalogChat();
  const deleteConversation = useDeleteConversation();
  const conversation = useConversation(conversationId);
  const projectUuid = conversation.data?.project_uuid ?? undefined;
  const project = useProject(projectUuid);
  const retrievalConfig = useRetrievalConfig(conversationId);
  const messagesQuery = useConversationMessages(conversationId);
  const {
    streamMessages,
    streamingMessageId,
    isStreaming,
    isCalculating,
    pendingInterrupt,
    sendMessage,
    sendResume,
  } = useWorkspaceConversation(conversationId, retrievalConfig);
  const isPositionChat = conversation.data?.prompt_type === 'ekt_calculator';
  const isKatalogChat = conversation.data?.prompt_type === 'katalog_chat';

  const onSlashCommand = (cmd: string) => {
    if (cmd === SLASH_CLEAR) {
      // Fresh thread: a new Katalog-Chat (global) or a project chat in the same project scope; the
      // old conversation stays in the list.
      if (isKatalogChat) void startKatalogChat();
      else if (projectUuid) void startProjectChat(projectUuid);
    } else if (cmd === SLASH_CLOSE) {
      navigate('/');
    } else if (cmd === SLASH_REMOVE) {
      // Delete this conversation and return to the dispatcher home.
      deleteConversation.mutate(conversationId, {
        onSuccess: () => navigate('/'),
      });
    }
  };

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

  // Show the ThinkingIndicator while a turn is streaming but no assistant text is open yet — the
  // wait after the user message (chat / calc start) and before the first reasoning line of a resume.
  const isThinking = isStreaming && streamingMessageId === null;

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
    isPositionChat ?
      (conversation.data?.title ?? 'EKT-Position')
    : isKatalogChat ?
      (conversation.data?.title ?? 'Katalog-Chat')
    : (project.data?.project_name ??
      conversation.data?.title ??
      'Project chat');

  // While a calculation is paused at a HITL gate, the structured panel replaces the chat input.
  const interrupt =
    pendingInterrupt ??
    derivePendingInterrupt(conversation.data, messagesQuery.data);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center border-b border-zinc-950/5 px-4 dark:border-white/5">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {title}
        </div>
      </header>
      <MessageList
        messages={merged}
        streamingMessageId={streamingMessageId}
        isThinking={isThinking}
        projectUuid={projectUuid}
        collapseStreamingReasoning={isCalculating}
      />

      {interrupt ?
        <InterruptPanel
          interrupt={interrupt}
          onResume={sendResume}
          disabled={isStreaming}
        />
      : <>
          {/* The catalog chat has no retrieval config (it queries the catalog via tools, not RAG). */}
          {!isKatalogChat && <RetrievalConfigBar conversationId={conversationId} />}
          <ChatInput
            onSend={sendMessage}
            onSlashCommand={onSlashCommand}
            slashCommands={PROJECT_CHAT_SLASH_COMMANDS}
            disabled={isStreaming}
            placeholder={
              isPositionChat ?
                'Über diese Position chatten, oder um die Kalkulation bitten…'
              : isKatalogChat ?
                'Frag den Katalog… (z. B. „Welche Lieferanten können AC 22 T S liefern?")'
              : 'Ask about this project… (/clear, /close, /remove)'
            }
            draftKey={`ws:${conversationId}`}
            hint={isStreaming ? 'Thinking…' : undefined}
          />
        </>
      }
    </div>
  );
}
