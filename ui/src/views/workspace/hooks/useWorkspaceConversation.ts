// Owns the dispatcher chat loop:
//   - reads persisted messages from the server (TanStack Query)
//   - layers the in-flight stream on top as ephemeral state
//   - exposes sendMessage() that POST→SSE-streams replies into the buffer
//
// Stream merge model:
//   - text_delta:           append to the open assistant message buffer
//   - function_call:        protocol-only; not shown in the chat
//   - function_call_output: on success, opens the main window for a routable
//                           tool (view_prompts / view_projects). Not shown
//                           inline.
//   - ui_notice:            append an ephemeral notice
//   - done:                 close the stream; the messages refetch flushes
//                           authoritative server-side ids
//
// After the first turn of a fresh conversation we kick off server-side
// auto-naming so the sidebar title stops reading "Untitled".

import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { postStream } from '../../../api/sse';
import { conversationKeys, useNameConversation } from '../../../api/conversations';
import { promptKeys } from '../../../api/prompts';
import { log } from '../../../lib/logger';
import { useUIStore } from '../../../store/ui';
import { useMainWindowStore, viewKindForTool } from '../../../store/mainWindow';
import type { MessageRead } from '../../../types/generated';
import type { DisplayMessage } from '../../../components/chat/types';

// IDs prefixed `local-` are placeholders until the server reconciles. The
// server-issued ids replace them on the next messages refetch.
function localId(prefix: string) {
  return `local-${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function newMessage(partial: Partial<MessageRead> & Pick<MessageRead, 'message_uuid' | 'kind'>): MessageRead {
  return {
    conversation_uuid: '',
    content: null,
    call_id: null,
    tool_name: null,
    arguments: null,
    success: null,
    data: null,
    errors: null,
    created_at: nowIso(),
    ...partial,
  };
}

interface StreamState {
  /** id of the currently-open assistant message (if any), so deltas append. */
  openAssistantId: string | null;
  /** map call_id → tool name, populated from function_call events. */
  toolNameByCallId: Record<string, string>;
}

export function useWorkspaceConversation(conversationId: string) {
  const qc = useQueryClient();
  const setStreamActive = useUIStore((s) => s.setStreamActive);
  const openMainWindow = useMainWindowStore((s) => s.openMainWindow);
  const nameConversation = useNameConversation();

  const [streamMessages, setStreamMessages] = useState<DisplayMessage[]>([]);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const streamStateRef = useRef<StreamState>({
    openAssistantId: null,
    toolNameByCallId: {},
  });
  const abortRef = useRef<AbortController | null>(null);

  // Read-only dispatcher tools don't strictly need invalidation, but keep
  // prompts fresh after a view_prompts call so the command view agrees.
  const invalidateForTool = useCallback(
    (toolName: string | null | undefined) => {
      if (toolName === 'view_prompts') {
        qc.invalidateQueries({ queryKey: promptKeys.all });
      }
    },
    [qc],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      // First turn iff no messages are persisted yet — drives auto-naming.
      const existing =
        qc.getQueryData<MessageRead[]>(conversationKeys.messages(conversationId)) ?? [];
      const isFirstTurn = existing.length === 0;

      const userMsg = newMessage({
        message_uuid: localId('user'),
        conversation_uuid: conversationId,
        kind: 'user',
        content: text,
      });
      setStreamMessages((prev) => [...prev, userMsg]);

      streamStateRef.current = { openAssistantId: null, toolNameByCallId: {} };
      setIsStreaming(true);
      setStreamActive(conversationId, true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const endTurnGroup = log.group.dispatcher('turn', {
        conversationId,
        text_len: text.length,
      });
      const toolGroupEnds: Record<string, () => void> = {};
      let textDeltaCount = 0;
      let textDeltaChars = 0;

      try {
        await postStream({
          path: `/conversations/${conversationId}/turn`,
          body: { content: text },
          signal: ctrl.signal,
          onEvent: (e) => {
            switch (e.event) {
              case 'text_delta': {
                textDeltaCount += 1;
                textDeltaChars += e.content.length;
                setStreamMessages((prev) => {
                  const openId = streamStateRef.current.openAssistantId;
                  if (openId) {
                    return prev.map((m) =>
                      m.message_uuid === openId && m.kind === 'assistant'
                        ? { ...m, content: (m.content ?? '') + e.content }
                        : m,
                    );
                  }
                  const id = localId('assistant');
                  streamStateRef.current.openAssistantId = id;
                  setStreamingMessageId(id);
                  const msg = newMessage({
                    message_uuid: id,
                    conversation_uuid: conversationId,
                    kind: 'assistant',
                    content: e.content,
                  });
                  return [...prev, msg];
                });
                break;
              }
              case 'function_call': {
                // Close any open assistant stream — a tool call follows.
                streamStateRef.current.openAssistantId = null;
                streamStateRef.current.toolNameByCallId[e.call_id] = e.name;
                toolGroupEnds[e.call_id] = log.group.tool(e.name, e.call_id);
                log.tool('args_keys', Object.keys(e.arguments));
                break;
              }
              case 'function_call_output': {
                const toolName =
                  e.tool_name ?? streamStateRef.current.toolNameByCallId[e.call_id] ?? null;
                log.tool('result', {
                  success: e.success,
                  has_data: e.data != null,
                  error_count: e.errors?.length ?? 0,
                });
                const endGroup = toolGroupEnds[e.call_id];
                if (endGroup) {
                  endGroup();
                  delete toolGroupEnds[e.call_id];
                }
                if (e.success) {
                  const kind = viewKindForTool(toolName);
                  if (kind) openMainWindow({ kind, data: e.data ?? undefined });
                  invalidateForTool(toolName);
                }
                break;
              }
              case 'ui_notice': {
                setStreamMessages((prev) => [
                  ...prev,
                  {
                    message_uuid: localId('note'),
                    conversation_uuid: conversationId,
                    kind: 'ui_notice',
                    content: e.content,
                    created_at: nowIso(),
                  },
                ]);
                break;
              }
              case 'done':
                streamStateRef.current.openAssistantId = null;
                setStreamingMessageId(null);
                log.dispatcher('turn complete', {
                  text_chunks: textDeltaCount,
                  text_chars: textDeltaChars,
                });
                break;
              default:
                break;
            }
          },
        });
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setStreamMessages((prev) => [
            ...prev,
            {
              message_uuid: localId('note'),
              conversation_uuid: conversationId,
              kind: 'ui_notice',
              content: `Stream failed: ${(err as Error).message}`,
              created_at: nowIso(),
            },
          ]);
        }
      } finally {
        for (const callId of Object.keys(toolGroupEnds)) {
          toolGroupEnds[callId]();
          delete toolGroupEnds[callId];
        }
        endTurnGroup();

        setIsStreaming(false);
        setStreamingMessageId(null);
        setStreamActive(conversationId, false);
        abortRef.current = null;

        // Land authoritative server messages before clearing placeholders so
        // there's no flash, then refresh the sidebar list (titles/timestamps).
        await qc.refetchQueries({ queryKey: conversationKeys.messages(conversationId) });
        setStreamMessages([]);
        qc.invalidateQueries({ queryKey: conversationKeys.all });

        // Auto-name a brand-new conversation from its first message.
        if (isFirstTurn) nameConversation.mutate(conversationId);
      }
    },
    [conversationId, qc, setStreamActive, invalidateForTool, openMainWindow, nameConversation],
  );

  return { streamMessages, streamingMessageId, isStreaming, sendMessage };
}
