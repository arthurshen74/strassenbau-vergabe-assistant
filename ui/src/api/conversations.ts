// Query/mutation hooks for conversations, wired to the real backend.
//
// The backend exposes a flat list of the user's conversations (no per-type
// filter, no GET-by-uuid, no rename/delete). Conversations are project chats;
// a conversation's title is generated server-side from its first message (see
// useNameConversation).

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { api } from './client';
import type {
  ConversationCostRead,
  ConversationCreate,
  ConversationRead,
  MessageRead,
} from '../types/generated';

export const PROMPT_TYPE_PROJECT_CHAT = 'project_chat';
export const PROMPT_TYPE_EKT_CALCULATOR = 'ekt_calculator';

export const conversationKeys = {
  all: ['conversations'] as const,
  list: () => [...conversationKeys.all, 'list'] as const,
  messages: (uuid: string) => ['conversation', uuid, 'messages'] as const,
  cost: (uuid: string) => ['conversation', uuid, 'cost'] as const,
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

// Total USD cost attributed to this conversation so far. Invalidated after each
// turn completes (see useWorkspaceConversation) so the running total stays fresh.
export function useConversationCost(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? conversationKeys.cost(uuid) : ['conversation', 'none', 'cost'],
    queryFn: () => api.get<ConversationCostRead>(`/conversations/${uuid}/cost`),
    enabled: !!uuid,
  });
}

// Create a conversation. Conversations are project chats; pass project_uuid to scope it.
export function createConversation(
  body: Partial<ConversationCreate> = {},
): Promise<ConversationRead> {
  return api.post<ConversationRead>('/conversations', {
    prompt_type: PROMPT_TYPE_PROJECT_CHAT,
    ...body,
  });
}

// Create a conversation and seed the list cache so ConversationRouter resolves
// the new thread immediately (no "not found" flash). Callers navigate to it.
export async function createAndSeedConversation(
  qc: QueryClient,
  body: Partial<ConversationCreate> = {},
): Promise<ConversationRead> {
  const created = await createConversation(body);
  qc.setQueryData<ConversationRead[]>(conversationKeys.list(), (old) =>
    old ? [created, ...old] : [created],
  );
  qc.invalidateQueries({ queryKey: conversationKeys.all });
  return created;
}

export function deleteConversation(uuid: string): Promise<void> {
  return api.delete<void>(`/conversations/${uuid}`);
}

// Delete a conversation (its messages cascade server-side) and refresh the list.
export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => deleteConversation(uuid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: conversationKeys.all });
    },
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
