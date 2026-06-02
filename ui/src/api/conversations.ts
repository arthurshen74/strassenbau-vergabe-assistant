// Query/mutation hooks for conversations, wired to the real backend.
//
// The backend exposes a flat list of the user's conversations (no per-type
// filter, no GET-by-uuid, no rename/delete). The dispatcher vs. project-chat
// split is derived client-side from `prompt_type`. A conversation's title is
// generated server-side from its first message (see useNameConversation).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { ConversationRead, MessageRead } from '../types/generated';

export const PROMPT_TYPE_DISPATCHER = 'dispatcher';
export const PROMPT_TYPE_PROJECT_CHAT = 'project_chat';

export const conversationKeys = {
  all: ['conversations'] as const,
  list: () => [...conversationKeys.all, 'list'] as const,
  messages: (uuid: string) => ['conversation', uuid, 'messages'] as const,
};

export function useConversationList() {
  return useQuery({
    queryKey: conversationKeys.list(),
    queryFn: () => api.get<ConversationRead[]>('/conversations'),
  });
}

// There is no GET /conversations/{uuid}; resolve from the list cache so we
// don't add a redundant backend route just to read one row.
export function useConversation(uuid: string | undefined) {
  const list = useConversationList();
  const data = uuid
    ? list.data?.find((c) => c.conversation_uuid === uuid)
    : undefined;
  return { ...list, data };
}

export function useConversationMessages(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid
      ? conversationKeys.messages(uuid)
      : ['conversation', 'none', 'messages'],
    queryFn: () => api.get<MessageRead[]>(`/conversations/${uuid}/messages`),
    enabled: !!uuid,
  });
}

export function createConversation(): Promise<ConversationRead> {
  return api.post<ConversationRead>('/conversations', {
    prompt_type: PROMPT_TYPE_DISPATCHER,
  });
}

// Generate a title from the conversation's first message and persist it.
// The backend derives the first message itself, so no body is sent.
export function useNameConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<ConversationRead>(`/conversations/${uuid}/name`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: conversationKeys.all });
    },
  });
}
