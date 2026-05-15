// Owns the prep session chat loop:
//   - startInitialTurn()  fired on mount when history is empty + in_progress
//   - sendAnswer(text)    POSTs a candidate answer, streams the next question
//   - submitCommand(cmd)  POSTs /exit; navigates on done
//   - opens GET /sessions/{id}/eval_stream in the background and keeps the
//     TanStack Query eval-score cache current via mergeEvalUpdate
//
// Mirrored after useWorkspaceConversation but simpler: no tool calls, no
// synthetic results.

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { postStream } from '../../../api/sse';
import { conversationKeys } from '../../../api/conversations';
import { sessionKeys } from '../../../api/sessions';
import { mergeEvalUpdate } from '../eval-merge';
import { apiBase } from '../../../api/client';
import { log } from '../../../lib/logger';
import type {
  CandidateMessageDTO,
  InterviewerMessageDTO,
  MessageDTO,
  UINoticeMessageDTO,
} from '../../../types/generated';

function localId(prefix: string) {
  return `local-${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}
function nowIso() {
  return new Date().toISOString();
}

export function usePrepSessionConversation(
  sessionId: string,
  workspaceConversationId: string | undefined,
) {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [streamMessages, setStreamMessages] = useState<MessageDTO[]>([]);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const answerAbortRef = useRef<AbortController | null>(null);
  const evalAbortRef = useRef<AbortController | null>(null);

  // ---------------------------------------------------------------------------
  // Eval stream — runs continuously in the background regardless of
  // drawer open/closed state. Feeds the TanStack Query eval-score cache.
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const ctrl = new AbortController();
    evalAbortRef.current = ctrl;

    async function openEvalStream() {
      try {
        const res = await fetch(`${apiBase}/sessions/${sessionId}/eval_stream`, {
          headers: { Accept: 'text/event-stream' },
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) return;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let sep: number;
          while ((sep = buffer.indexOf('\n\n')) !== -1) {
            const raw = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);

            // Skip SSE comment lines (heartbeats: ": heartbeat")
            if (raw.trim().startsWith(':')) continue;

            let eventName = '';
            let dataLine = '';
            for (const line of raw.split('\n')) {
              if (line.startsWith('event:')) eventName = line.slice(6).trim();
              else if (line.startsWith('data:')) dataLine = line.slice(5).trim();
            }
            if (eventName !== 'eval_update' || !dataLine) continue;

            try {
              const event = JSON.parse(dataLine);
              qc.setQueryData(
                sessionKeys.evalScores(sessionId),
                (prev: Record<string, unknown> | undefined) =>
                  mergeEvalUpdate(prev as Parameters<typeof mergeEvalUpdate>[0], event),
              );
            } catch {
              // malformed event — skip
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          log.sse.error('eval_stream_error', { sessionId, err });
        }
      }
    }

    openEvalStream();
    return () => ctrl.abort();
  }, [sessionId, qc]);

  // ---------------------------------------------------------------------------
  // Cleanup answer stream on unmount
  // ---------------------------------------------------------------------------

  useEffect(() => {
    return () => {
      answerAbortRef.current?.abort();
      evalAbortRef.current?.abort();
    };
  }, []);

  // ---------------------------------------------------------------------------
  // startInitialTurn — called by PrepSessionView on mount when history is
  // empty and session is in_progress
  // ---------------------------------------------------------------------------

  const startInitialTurn = useCallback(async () => {
    setIsStreaming(true);
    const ctrl = new AbortController();
    answerAbortRef.current = ctrl;

    try {
      await postStream({
        path: `/sessions/${sessionId}/initial_turn`,
        body: {},
        signal: ctrl.signal,
        onEvent: (e) => {
          switch (e.event) {
            case 'interviewer_delta': {
              setStreamMessages((prev) => {
                const open = prev.find(
                  (m): m is InterviewerMessageDTO =>
                    m.kind === 'interviewer_message' && m.id.startsWith('local-'),
                );
                if (open) {
                  return prev.map((m) =>
                    m.id === open.id
                      ? { ...m, content: (m as InterviewerMessageDTO).content + e.content }
                      : m,
                  );
                }
                const id = localId('interviewer');
                setStreamingMessageId(id);
                const msg: InterviewerMessageDTO = {
                  id,
                  conversation_id: sessionId,
                  created_at: nowIso(),
                  kind: 'interviewer_message',
                  content: e.content,
                  question_number: e.question_number,
                };
                return [...prev, msg];
              });
              break;
            }
            case 'ui_notice': {
              setStreamMessages((prev) => [
                ...prev,
                {
                  id: localId('note'),
                  conversation_id: sessionId,
                  created_at: nowIso(),
                  kind: 'ui_notice',
                  content: e.content,
                } satisfies UINoticeMessageDTO,
              ]);
              break;
            }
            case 'done':
              setStreamingMessageId(null);
              break;
            case 'error':
              setStreamingMessageId(null);
              log.sse.error('initial_turn_backend_error', { message: e.message });
              setStreamMessages((prev) => [
                ...prev,
                {
                  id: localId('note'),
                  conversation_id: sessionId,
                  created_at: nowIso(),
                  kind: 'ui_notice',
                  content: `Could not start the interview: ${e.message}`,
                } satisfies UINoticeMessageDTO,
              ]);
              break;
            default:
              break;
          }
        },
      });
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        log.sse.error('initial_turn_error', { sessionId, err });
      }
    } finally {
      setIsStreaming(false);
      setStreamingMessageId(null);
      answerAbortRef.current = null;
      await qc.refetchQueries({ queryKey: conversationKeys.messages(sessionId) });
      setStreamMessages([]);
      qc.invalidateQueries({ queryKey: conversationKeys.all });
    }
  }, [sessionId, qc]);

  // ---------------------------------------------------------------------------
  // sendAnswer — candidate submits a response to the interviewer's question
  // ---------------------------------------------------------------------------

  const sendAnswer = useCallback(
    async (text: string) => {
      // Optimistic candidate message
      const candidateMsg: CandidateMessageDTO = {
        id: localId('candidate'),
        conversation_id: sessionId,
        created_at: nowIso(),
        kind: 'candidate_message',
        content: text,
      };
      setStreamMessages((prev) => [...prev, candidateMsg]);
      setIsStreaming(true);
      const ctrl = new AbortController();
      answerAbortRef.current = ctrl;

      try {
        await postStream({
          path: `/sessions/${sessionId}/messages`,
          body: { content: text },
          signal: ctrl.signal,
          onEvent: (e) => {
            switch (e.event) {
              case 'interviewer_delta': {
                setStreamMessages((prev) => {
                  const open = prev.find(
                    (m): m is InterviewerMessageDTO =>
                      m.kind === 'interviewer_message' && m.id.startsWith('local-'),
                  );
                  if (open) {
                    return prev.map((m) =>
                      m.id === open.id
                        ? { ...m, content: (m as InterviewerMessageDTO).content + e.content }
                        : m,
                    );
                  }
                  const id = localId('interviewer');
                  setStreamingMessageId(id);
                  const msg: InterviewerMessageDTO = {
                    id,
                    conversation_id: sessionId,
                    created_at: nowIso(),
                    kind: 'interviewer_message',
                    content: e.content,
                    question_number: e.question_number,
                  };
                  return [...prev, msg];
                });
                break;
              }
              case 'ui_notice': {
                setStreamMessages((prev) => [
                  ...prev,
                  {
                    id: localId('note'),
                    conversation_id: sessionId,
                    created_at: nowIso(),
                    kind: 'ui_notice',
                    content: e.content,
                  } satisfies UINoticeMessageDTO,
                ]);
                break;
              }
              case 'done':
                setStreamingMessageId(null);
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
              id: localId('note'),
              conversation_id: sessionId,
              created_at: nowIso(),
              kind: 'ui_notice',
              content: `Stream failed: ${(err as Error).message}`,
            } satisfies UINoticeMessageDTO,
          ]);
        }
      } finally {
        setIsStreaming(false);
        setStreamingMessageId(null);
        answerAbortRef.current = null;
        // Refetch both messages AND the conversation detail synchronously so
        // the header (question_count, status) and ChatInput disabled state
        // update before the next render. Using invalidateQueries here causes
        // a window where the session looks in_progress after completion.
        await Promise.all([
          qc.refetchQueries({ queryKey: conversationKeys.messages(sessionId) }),
          qc.refetchQueries({ queryKey: conversationKeys.detail(sessionId) }),
        ]);
        setStreamMessages([]);
        qc.invalidateQueries({ queryKey: conversationKeys.all });
      }
    },
    [sessionId, qc],
  );

  // ---------------------------------------------------------------------------
  // submitCommand — /exit only
  // ---------------------------------------------------------------------------

  const submitCommand = useCallback(
    async (cmd: '/exit') => {
      setIsStreaming(true);
      const ctrl = new AbortController();
      answerAbortRef.current = ctrl;

      try {
        await postStream({
          path: `/sessions/${sessionId}/commands`,
          body: { command: cmd },
          signal: ctrl.signal,
          onEvent: (e) => {
            if (e.event === 'ui_notice') {
              setStreamMessages((prev) => [
                ...prev,
                {
                  id: localId('note'),
                  conversation_id: sessionId,
                  created_at: nowIso(),
                  kind: 'ui_notice',
                  content: e.content,
                } satisfies UINoticeMessageDTO,
              ]);
            }
          },
        });
      } finally {
        setIsStreaming(false);
        answerAbortRef.current = null;
        // Refresh the conversation so the sidebar reflects the new status.
        qc.invalidateQueries({ queryKey: conversationKeys.detail(sessionId) });
        qc.invalidateQueries({ queryKey: conversationKeys.all });
        // Navigate back to workspace.
        if (workspaceConversationId) {
          navigate(`/c/${workspaceConversationId}`);
        } else {
          navigate('/');
        }
      }
    },
    [sessionId, workspaceConversationId, navigate, qc],
  );

  return {
    streamMessages,
    streamingMessageId,
    isStreaming,
    startInitialTurn,
    sendAnswer,
    submitCommand,
  };
}
