// Session-specific query hooks and mutations.
//
// Conversation header and message history come from the existing
// useConversation / useConversationMessages in api/conversations.ts —
// PrepSessionConversation is a Conversation, so those endpoints serve both.
// This file covers only session-specific resources: eval scores, and the
// start mutation used by workspace tool result handlers.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { conversationKeys } from './conversations';
import type { EvalScoreDTO, PrepSessionConversationDTO } from '../types/generated';

export const sessionKeys = {
  evalScores: (id: string) => ['session', id, 'eval_scores'] as const,
};

// ---------------------------------------------------------------------------
// Eval scores — seeds the TanStack Query cache on load/resume.
// The eval-stream listener (in usePrepSessionConversation) splices live
// updates into this same cache via queryClient.setQueryData.
// ---------------------------------------------------------------------------

export function useEvalScores(sessionId: string | undefined) {
  return useQuery({
    queryKey: sessionId ? sessionKeys.evalScores(sessionId) : ['session', 'none', 'eval_scores'],
    queryFn: () =>
      api.get<Record<string, EvalScoreDTO>>(`/sessions/${sessionId}/eval_scores`),
    enabled: !!sessionId,
  });
}

// ---------------------------------------------------------------------------
// Mutations — used by workspace tool result renderers to navigate into
// a session after the dispatcher creates one.
// ---------------------------------------------------------------------------

export function useStartPrepSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      position_id: string;
      target_question_count: number;
      evaluator_prompt_id?: string;
      interviewer_prompt_id?: string;
    }) => api.post<PrepSessionConversationDTO>('/sessions', args),
    onSuccess: (data) => {
      // Prime the conversation detail cache so the router renders
      // immediately without a loading flash when navigating into the session.
      qc.setQueryData(conversationKeys.detail(data.id), data);
      qc.invalidateQueries({ queryKey: conversationKeys.all });
    },
  });
}

export function useDeletePrepSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      api.delete<PrepSessionConversationDTO>(`/sessions/${sessionId}`),
    onSuccess: (_data, sessionId) => {
      // Remove cached detail/messages for the deleted session and refresh
      // the sidebar list (same pattern as useDeleteConversation).
      qc.removeQueries({ queryKey: conversationKeys.detail(sessionId) });
      qc.removeQueries({ queryKey: conversationKeys.messages(sessionId) });
      qc.invalidateQueries({ queryKey: conversationKeys.all });
    },
  });
}
