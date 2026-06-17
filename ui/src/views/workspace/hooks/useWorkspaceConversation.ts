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
//   - ui_notice:            append a notice (error-styled when level==='error');
//                           never persisted, so it's retained across the refetch
//                           and cleared on the next turn
//   - done:                 close the stream; the messages refetch flushes
//                           authoritative server-side ids
//
// After the first turn of a fresh conversation we kick off server-side
// auto-naming so the sidebar title stops reading "Untitled".

import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { postStream } from '../../../api/sse';
import { conversationKeys, useNameConversation } from '../../../api/conversations';
import type { CalculationResume } from '../../../api/calculations';
import { promptKeys } from '../../../api/prompts';
import { log } from '../../../lib/logger';
import { useUIStore } from '../../../store/ui';
import { useMainWindowStore, viewKindForTool } from '../../../store/mainWindow';
import type { MessageRead, TurnRetrievalConfig } from '../../../types/generated';
import type { DisplayMessage } from '../../../components/chat/types';

// A paused EKT calculation awaiting the Kalkulator's structured decision at a HITL gate.
export interface PendingInterrupt {
  stage: string;
  payload: Record<string, unknown>;
}

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

export function useWorkspaceConversation(
  conversationId: string,
  retrievalConfig?: TurnRetrievalConfig,
) {
  const qc = useQueryClient();
  const setStreamActive = useUIStore((s) => s.setStreamActive);
  const openMainWindow = useMainWindowStore((s) => s.openMainWindow);
  const nameConversation = useNameConversation();

  const [streamMessages, setStreamMessages] = useState<DisplayMessage[]>([]);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingInterrupt, setPendingInterrupt] = useState<PendingInterrupt | null>(null);
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

  // One streaming turn: `body` is either {content} (a chat message, possibly kicking off the
  // calculation) or {resume} (a structured HITL decision). `userText` adds the user bubble for a
  // chat message; null for a resume (it's answered structurally, not as a chat turn).
  const runTurn = useCallback(
    async (body: Record<string, unknown>, userText: string | null) => {
      // First turn iff no messages are persisted yet — drives auto-naming.
      const existing =
        qc.getQueryData<MessageRead[]>(conversationKeys.messages(conversationId)) ?? [];
      const isFirstTurn = existing.length === 0;

      // Drop notices retained from a prior turn; add the user bubble for a chat message.
      setStreamMessages((prev) => {
        const cleaned = prev.filter((m) => m.kind !== 'ui_notice');
        if (userText === null) return cleaned;
        return [
          ...cleaned,
          newMessage({
            message_uuid: localId('user'),
            conversation_uuid: conversationId,
            kind: 'user',
            content: userText,
          }),
        ];
      });
      setPendingInterrupt(null);

      streamStateRef.current = { openAssistantId: null, toolNameByCallId: {} };
      setIsStreaming(true);
      setStreamActive(conversationId, true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const endTurnGroup = log.group.dispatcher('turn', {
        conversationId,
        text_len: userText?.length ?? 0,
      });
      const toolGroupEnds: Record<string, () => void> = {};
      let textDeltaCount = 0;
      let textDeltaChars = 0;

      try {
        await postStream({
          path: `/conversations/${conversationId}/turn`,
          body,
          signal: ctrl.signal,
          onEvent: (e) => {
            switch (e.event) {
              case 'text_delta': {
                textDeltaCount += 1;
                textDeltaChars += e.content.length;
                // The side effects (new id, the openAssistantId ref write, setStreamingMessageId)
                // run HERE in the event callback, never inside the setStreamMessages updater:
                // StrictMode double-invokes updaters, and an impure updater would set the ref on the
                // first invoke then take the wrong branch on the second and silently drop the
                // message. The updaters below are pure (idempotent under double-invocation).
                if (streamStateRef.current.openAssistantId === null) {
                  const id = localId('assistant');
                  streamStateRef.current.openAssistantId = id;
                  setStreamingMessageId(id);
                  const msg = newMessage({
                    message_uuid: id,
                    conversation_uuid: conversationId,
                    kind: 'assistant',
                    content: e.content,
                  });
                  setStreamMessages((prev) => [...prev, msg]);
                } else {
                  const openId = streamStateRef.current.openAssistantId;
                  setStreamMessages((prev) =>
                    prev.map((m) =>
                      m.message_uuid === openId && m.kind === 'assistant'
                        ? { ...m, content: (m.content ?? '') + e.content }
                        : m,
                    ),
                  );
                }
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
                  if (kind) {
                    // Dispatcher tools open the main window instead of rendering inline.
                    openMainWindow({ kind, data: e.data ?? undefined });
                    invalidateForTool(toolName);
                  } else {
                    // Project-chat tools (LV results, retrieval sources) render in the thread.
                    setStreamMessages((prev) => [
                      ...prev,
                      newMessage({
                        message_uuid: localId('tool'),
                        conversation_uuid: conversationId,
                        kind: 'function_call_output',
                        call_id: e.call_id,
                        tool_name: toolName,
                        success: e.success,
                        data: e.data ?? null,
                        errors: e.errors ?? null,
                      }),
                    ]);
                  }
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
                    level: e.level,
                    created_at: nowIso(),
                  },
                ]);
                break;
              }
              case 'interrupt':
                // The calculation paused at a HITL gate; park it so the InterruptPanel can render.
                streamStateRef.current.openAssistantId = null;
                setStreamingMessageId(null);
                setPendingInterrupt({ stage: e.stage, payload: e.payload });
                break;
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
              content: 'Sorry, the connection was interrupted. Please try again.',
              level: 'error',
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
        // Notices are never persisted server-side, so retain them across the
        // refetch — otherwise an error notice flashes and vanishes.
        await qc.refetchQueries({ queryKey: conversationKeys.messages(conversationId) });
        setStreamMessages((prev) => prev.filter((m) => m.kind === 'ui_notice'));
        qc.invalidateQueries({ queryKey: conversationKeys.all });
        // The turn's LLM calls just landed usage rows; refresh the running cost.
        qc.invalidateQueries({ queryKey: conversationKeys.cost(conversationId) });

        // Auto-name a brand-new conversation from its first message.
        if (isFirstTurn) nameConversation.mutate(conversationId);
      }
    },
    [
      conversationId,
      qc,
      setStreamActive,
      invalidateForTool,
      openMainWindow,
      nameConversation,
    ],
  );

  const sendMessage = useCallback(
    (text: string) =>
      runTurn(
        retrievalConfig ? { content: text, retrieval: retrievalConfig } : { content: text },
        text,
      ),
    [runTurn, retrievalConfig],
  );

  // Answer the current HITL gate; the calculation continues streaming in this turn.
  const sendResume = useCallback(
    (decision: CalculationResume) => runTurn({ resume: decision }, null),
    [runTurn],
  );

  return {
    streamMessages,
    streamingMessageId,
    isStreaming,
    pendingInterrupt,
    sendMessage,
    sendResume,
  };
}
