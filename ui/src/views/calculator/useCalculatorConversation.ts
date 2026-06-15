// Drives the live phase of an ekt_calculator conversation: opens the run stream (or a resume), merges
// the SSE into an ephemeral message buffer (assistant text + the ekt_result card), and parks a
// pendingInterrupt when the run pauses for the Kalkulator. Once a segment ends, the persisted
// messages are refetched and the buffer is cleared, so the transcript is authoritative.

import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  resumeCalculation,
  streamCalculation,
  type CalculationResume,
} from '../../api/calculations';
import { conversationKeys } from '../../api/conversations';
import type { MessageRead, SSEEvent } from '../../types/generated';
import type { DisplayMessage } from '../../components/chat/types';

export interface PendingInterrupt {
  stage: string;
  payload: Record<string, unknown>;
}

function localId(prefix: string) {
  return `local-${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function newMessage(
  partial: Partial<MessageRead> & Pick<MessageRead, 'message_uuid' | 'kind'>,
): MessageRead {
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

export function useCalculatorConversation(conversationId: string) {
  const qc = useQueryClient();
  const [streamMessages, setStreamMessages] = useState<DisplayMessage[]>([]);
  const [pendingInterrupt, setPendingInterrupt] = useState<PendingInterrupt | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const openAssistantId = useRef<string | null>(null);

  const onEvent = useCallback(
    (e: SSEEvent) => {
      switch (e.event) {
        case 'text_delta': {
          setStreamMessages((prev) => {
            const openId = openAssistantId.current;
            if (openId) {
              return prev.map((m) =>
                m.message_uuid === openId && m.kind === 'assistant'
                  ? { ...m, content: (m.content ?? '') + e.content }
                  : m,
              );
            }
            const id = localId('assistant');
            openAssistantId.current = id;
            return [
              ...prev,
              newMessage({
                message_uuid: id,
                conversation_uuid: conversationId,
                kind: 'assistant',
                content: e.content,
              }),
            ];
          });
          break;
        }
        case 'function_call':
          openAssistantId.current = null;
          break;
        case 'function_call_output':
          openAssistantId.current = null;
          if (e.success) {
            setStreamMessages((prev) => [
              ...prev,
              newMessage({
                message_uuid: localId('tool'),
                conversation_uuid: conversationId,
                kind: 'function_call_output',
                call_id: e.call_id,
                tool_name: e.tool_name ?? null,
                success: e.success,
                data: e.data ?? null,
                errors: e.errors ?? null,
              }),
            ]);
          }
          break;
        case 'interrupt':
          openAssistantId.current = null;
          setPendingInterrupt({ stage: e.stage, payload: e.payload });
          break;
        case 'ui_notice':
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
        case 'done':
          openAssistantId.current = null;
          break;
        default:
          break;
      }
    },
    [conversationId],
  );

  const runSegment = useCallback(
    async (fn: () => Promise<void>) => {
      setIsStreaming(true);
      setPendingInterrupt(null);
      try {
        await fn();
      } catch {
        setStreamMessages((prev) => [
          ...prev,
          {
            message_uuid: localId('note'),
            conversation_uuid: conversationId,
            kind: 'ui_notice',
            content: 'Sorry, the calculation stream was interrupted. Please try again.',
            level: 'error',
            created_at: nowIso(),
          },
        ]);
      } finally {
        setIsStreaming(false);
        qc.invalidateQueries({ queryKey: conversationKeys.all });
        // Land authoritative persisted messages, then drop placeholders (keep notices).
        await qc.refetchQueries({ queryKey: conversationKeys.messages(conversationId) });
        setStreamMessages((prev) => prev.filter((m) => m.kind === 'ui_notice'));
        qc.invalidateQueries({ queryKey: conversationKeys.cost(conversationId) });
      }
    },
    [qc, conversationId],
  );

  const startStream = useCallback(
    () => runSegment(() => streamCalculation({ conversationId, onEvent })),
    [runSegment, conversationId, onEvent],
  );

  const resume = useCallback(
    (decision: CalculationResume) =>
      runSegment(() => resumeCalculation({ conversationId, decision, onEvent })),
    [runSegment, conversationId, onEvent],
  );

  return { streamMessages, pendingInterrupt, isStreaming, startStream, resume };
}
