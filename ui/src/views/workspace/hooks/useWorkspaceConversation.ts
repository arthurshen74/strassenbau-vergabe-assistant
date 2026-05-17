// Single hook that owns the workspace chat loop:
//   - reads persisted messages from the server (TanStack Query)
//   - layers the in-flight stream on top as ephemeral state
//   - exposes a sendMessage() that POST→SSE-streams replies and merges
//     events into the local stream buffer
//
// Why a hook (vs. moving this into the WorkspaceView component): the same
// loop will be needed once we add session resumption / reconnection. Also
// keeps the view free of fetch/abort plumbing.
//
// Stream merge model:
//   - text_delta:           append to current `assistant_message` buffer
//                           (creating one if none open)
//   - function_call:        appended as a hidden FunctionCallMessageDTO
//                           so the call_id ↔ output pairing exists in
//                           one place when the output arrives.
//   - function_call_output: appended as a FunctionCallOutputMessageDTO.
//                           Tool name resolved from the matching
//                           function_call by call_id.
//   - ui_notice:            append a UINoticeMessageDTO.
//   - done / error:         close the stream; query invalidation flushes
//                           authoritative server-side IDs.

import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { postStream } from '../../../api/sse';
import { conversationKeys } from '../../../api/conversations';
import { positionKeys } from '../../../api/positions';
import { promptKeys } from '../../../api/prompts';
import { log } from '../../../lib/logger';
import { useUIStore } from '../../../store/ui';
import type {
  AssistantMessageDTO,
  FunctionCallMessageDTO,
  FunctionCallOutputMessageDTO,
  MessageDTO,
  UINoticeMessageDTO,
  UserMessageDTO,
} from '../../../types/generated';

// View-level flows (pasted-text save, etc.) sometimes want
// to render an inline tool-result card without going through the
// dispatcher LLM. We synthesize a FunctionCallOutputMessageDTO so the
// existing ToolResultRouter can render it just like a real one. The
// `tool_name` here must match a real tool — it's the discriminator the
// router uses to pick a renderer.
export type SyntheticToolName =
  | 'add_position'
  | 'modify_position'
  | 'view_position'
  | 'archive_position'
  | 'view_prompt'
  | 'edit_prompt'
  | 'archive_prompt';

// IDs prefixed `local-` are placeholders until the server reconciles. The
// server-issued IDs replace them on the next messages refetch.
function localId(prefix: string) {
  return `local-${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function nowIso() {
  return new Date().toISOString();
}

interface StreamState {
  /** id of the currently-open assistant_message (if any), so deltas append. */
  openAssistantId: string | null;
  /** map call_id → tool name, populated from function_call events. */
  toolNameByCallId: Record<string, string>;
}

export function useWorkspaceConversation(conversationId: string) {
  const qc = useQueryClient();
  const setStreamActive = useUIStore((s) => s.setStreamActive);

  // Locally-buffered messages that haven't been reconciled with the
  // server yet. We keep them separate from the query cache so an
  // accidental refetch doesn't blow them away mid-stream.
  const [streamMessages, setStreamMessages] = useState<MessageDTO[]>([]);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const streamStateRef = useRef<StreamState>({
    openAssistantId: null,
    toolNameByCallId: {},
  });
  const abortRef = useRef<AbortController | null>(null);

  // Invalidations triggered when a tool call mutates server resources.
  // Keyed off tool name; expand as new mutating tools land.
  const invalidateForTool = useCallback(
    (toolName: string | null | undefined) => {
      if (!toolName) return;
      switch (toolName) {
        case 'list_positions':
        case 'add_position':
        case 'modify_position':
        case 'archive_position':
          qc.invalidateQueries({ queryKey: positionKeys.all });
          break;
        case 'list_prompts':
        case 'view_prompt':
        case 'edit_prompt':
        case 'archive_prompt':
          qc.invalidateQueries({ queryKey: promptKeys.all });
          break;
      }
    },
    [qc],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      // optimistic user message
      const userMsg: UserMessageDTO = {
        id: localId('user'),
        conversation_id: conversationId,
        created_at: nowIso(),
        kind: 'user_message',
        content: text,
      };
      setStreamMessages((prev) => [...prev, userMsg]);

      streamStateRef.current = {
        openAssistantId: null,
        toolNameByCallId: {},
      };
      setIsStreaming(true);
      setStreamActive(conversationId, true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const endTurnGroup = log.group.dispatcher('turn', {
        conversationId,
        text_len: text.length,
      });
      // Each function_call event opens a tool group; the matching
      // function_call_output closes it. Track open groups by call_id so
      // an out-of-order or missing output doesn't strand a frame.
      const toolGroupEnds: Record<string, () => void> = {};
      let textDeltaCount = 0;
      let textDeltaChars = 0;

      try {
        await postStream({
          path: `/conversations/${conversationId}/messages`,
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
                      m.id === openId && m.kind === 'assistant_message'
                        ? { ...m, content: m.content + e.content }
                        : m,
                    );
                  }
                  const id = localId('assistant');
                  streamStateRef.current.openAssistantId = id;
                  setStreamingMessageId(id);
                  const msg: AssistantMessageDTO = {
                    id,
                    conversation_id: conversationId,
                    created_at: nowIso(),
                    kind: 'assistant_message',
                    content: e.content,
                  };
                  return [...prev, msg];
                });
                break;
              }
              case 'function_call': {
                // close any open assistant stream — a tool call follows.
                streamStateRef.current.openAssistantId = null;
                streamStateRef.current.toolNameByCallId[e.call_id] = e.name;
                toolGroupEnds[e.call_id] = log.group.tool(e.name, e.call_id);
                log.tool('args_keys', Object.keys(e.arguments));
                const fc: FunctionCallMessageDTO = {
                  id: localId('fc'),
                  conversation_id: conversationId,
                  created_at: nowIso(),
                  kind: 'function_call',
                  name: e.name,
                  arguments: e.arguments,
                  call_id: e.call_id,
                };
                setStreamMessages((prev) => [...prev, fc]);
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
                if (e.data != null) {
                  log.tool('data', e.data);
                }
                const endGroup = toolGroupEnds[e.call_id];
                if (endGroup) {
                  endGroup();
                  delete toolGroupEnds[e.call_id];
                }
                const out: FunctionCallOutputMessageDTO = {
                  id: localId('fco'),
                  conversation_id: conversationId,
                  created_at: nowIso(),
                  kind: 'function_call_output',
                  call_id: e.call_id,
                  tool_name: toolName,
                  success: e.success,
                  data: e.data ?? null,
                  errors: e.errors ?? null,
                };
                setStreamMessages((prev) => [...prev, out]);
                if (e.success) invalidateForTool(toolName);
                break;
              }
              case 'ui_notice': {
                const note: UINoticeMessageDTO = {
                  id: localId('note'),
                  conversation_id: conversationId,
                  created_at: nowIso(),
                  kind: 'ui_notice',
                  content: e.content,
                };
                setStreamMessages((prev) => [...prev, note]);
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
              case 'error':
                streamStateRef.current.openAssistantId = null;
                setStreamingMessageId(null);
                log.dispatcher.error('turn errored', { message: e.message });
                // Surface as a UI notice so the user sees something.
                setStreamMessages((prev) => [
                  ...prev,
                  {
                    id: localId('note'),
                    conversation_id: conversationId,
                    created_at: nowIso(),
                    kind: 'ui_notice',
                    content: `Error: ${e.message}`,
                  },
                ]);
                break;
              default:
                break;
            }
          },
        });
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          // Surface unexpected stream failures as a UI notice.
          setStreamMessages((prev) => [
            ...prev,
            {
              id: localId('note'),
              conversation_id: conversationId,
              created_at: nowIso(),
              kind: 'ui_notice',
              content: `Stream failed: ${(err as Error).message}`,
            },
          ]);
        }
      } finally {
        // Close any tool groups whose function_call_output never arrived
        // (e.g. stream aborted mid-tool) before closing the dispatcher
        // group, so the console nesting stays balanced.
        for (const callId of Object.keys(toolGroupEnds)) {
          toolGroupEnds[callId]();
          delete toolGroupEnds[callId];
        }
        endTurnGroup();

        setIsStreaming(false);
        setStreamingMessageId(null);
        setStreamActive(conversationId, false);
        abortRef.current = null;

        // Refetch the persisted message list so server-issued IDs are
        // authoritative before we clear the local placeholders. We await
        // the messages refetch so there's no flash: the server data lands
        // first, then the local stream buffer is cleared. The conversations
        // list invalidation is fire-and-forget (just refreshes title/ts).
        await qc.refetchQueries({ queryKey: conversationKeys.messages(conversationId) });
        setStreamMessages([]);
        qc.invalidateQueries({ queryKey: conversationKeys.all });
      }
    },
    [conversationId, qc, setStreamActive, invalidateForTool],
  );

  // Resets the local buffer once the server has the same content (caller
  // decides; today we never reset and rely on the server messages list to
  // be authoritative once it returns the same ids).
  const clearStreamBuffer = useCallback(() => {
    setStreamMessages([]);
  }, []);

  // Drop a transient ui_notice into the local stream. Used by view-level
  // flows that want to leave a breadcrumb in the chat without going
  // through the dispatcher. These notices live only in client state —
  // they don't hit the server and disappear on reload.
  const appendUiNotice = useCallback(
    (content: string) => {
      setStreamMessages((prev) => [
        ...prev,
        {
          id: localId('note'),
          conversation_id: conversationId,
          created_at: nowIso(),
          kind: 'ui_notice',
          content,
        },
      ]);
      qc.invalidateQueries({ queryKey: conversationKeys.all });
    },
    [conversationId, qc],
  );

  // Push a synthetic tool-result message into the local stream. View
  // flows that bypass the dispatcher (paste-position saves, etc.) use
  // this so the chat shows the same inline card the LLM-driven path
  // would produce. We mark the message as success=true; failed results
  // would be filtered by MessageList.
  //
  // Because these are local-only and never persisted server-side, they
  // disappear on reload — the authoritative position card can be
  // recovered via the dispatcher ("show me my positions"). That's a
  // deliberate trade-off: persisting client-initiated tool-result
  // synthetics would muddle the dispatcher's view of conversation history.
  const appendToolResult = useCallback(
    (toolName: SyntheticToolName, data: Record<string, unknown>) => {
      setStreamMessages((prev) => [
        ...prev,
        {
          id: localId('fco'),
          conversation_id: conversationId,
          created_at: nowIso(),
          kind: 'function_call_output',
          call_id: localId('local-call'),
          tool_name: toolName,
          success: true,
          data,
          errors: null,
        },
      ]);
      qc.invalidateQueries({ queryKey: conversationKeys.all });
    },
    [conversationId, qc],
  );

  return {
    streamMessages,
    streamingMessageId,
    isStreaming,
    sendMessage,
    clearStreamBuffer,
    appendUiNotice,
    appendToolResult,
  };
}
