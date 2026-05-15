// Query/mutation hooks for conversations. Workspace-only at this stage;
// prep_session and judge_run hooks will plug in later as those views land.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  ConversationDTO,
  ConversationSummaryDTO,
  MessageDTO,
} from '../types/generated';

export const conversationKeys = {
  all: ['conversations'] as const,
  list: (type?: string) => [...conversationKeys.all, { type }] as const,
  detail: (id: string) => ['conversation', id] as const,
  messages: (id: string) => ['conversation', id, 'messages'] as const,
};

export function useConversationList(
  type?: 'workspace' | 'prep_session' | 'judge_run',
) {
  return useQuery({
    queryKey: conversationKeys.list(type),
    queryFn: () =>
      api.get<ConversationSummaryDTO[]>(
        `/conversations${type ? `?type=${type}` : ''}`,
      ),
  });
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: id ? conversationKeys.detail(id) : ['conversation', 'none'],
    queryFn: () => api.get<ConversationDTO>(`/conversations/${id}`),
    enabled: !!id,
  });
}

export function useConversationMessages(id: string | undefined) {
  return useQuery({
    queryKey: id ? conversationKeys.messages(id) : ['conversation', 'none', 'messages'],
    queryFn: () => api.get<MessageDTO[]>(`/conversations/${id}/messages`),
    enabled: !!id,
  });
}

export function useRenameConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      api.patch<ConversationDTO>(`/conversations/${id}`, { title }),
    onSuccess: (updated) => {
      // Refresh the sidebar list so the new title shows immediately.
      qc.invalidateQueries({ queryKey: conversationKeys.all });
      // Update the cached detail so the conversation view header stays in sync.
      qc.setQueryData(conversationKeys.detail(updated.id), updated);
    },
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/conversations/${id}`),
    onSuccess: (_data, id) => {
      // Drop cached detail/messages for the deleted thread and refresh
      // the sidebar list. Removing (vs. invalidating) the detail keys
      // avoids a flash of stale data if the user is currently viewing
      // the thread being deleted.
      qc.removeQueries({ queryKey: conversationKeys.detail(id) });
      qc.removeQueries({ queryKey: conversationKeys.messages(id) });
      qc.invalidateQueries({ queryKey: conversationKeys.all });
    },
  });
}
