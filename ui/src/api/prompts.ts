// TanStack Query hooks for prompts plus a thin SSE wrapper for the
// "test prompt" feature. The test endpoint accepts a multi-turn
// transcript and streams an assistant response — same SSE shape as
// the dispatcher, so we reuse `postStream`.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { postStream } from './sse';
import type {
  EditPromptBody,
  IPAPrompt,
  PromptGroupDTO,
  PromptSummaryDTO,
  SSEEvent,
  TestPromptMessage,
} from '../types/generated';

export const promptKeys = {
  all: ['prompts'] as const,
  list: (filter?: { prompt_type?: IPAPrompt; include_archived?: boolean }) =>
    ['prompts', 'list', filter ?? {}] as const,
  group: (prompt_type: IPAPrompt, name: string) =>
    ['prompt', prompt_type, name] as const,
};

export interface ListPromptsFilter {
  prompt_type?: IPAPrompt;
  name_search?: string;
  include_archived?: boolean;
}

export function usePrompts(filter: ListPromptsFilter = {}) {
  const params = new URLSearchParams();
  if (filter.prompt_type) params.set('prompt_type', filter.prompt_type);
  if (filter.name_search) params.set('name_search', filter.name_search);
  if (filter.include_archived) params.set('include_archived', 'true');
  const qs = params.toString();
  return useQuery({
    queryKey: promptKeys.list({
      prompt_type: filter.prompt_type,
      include_archived: filter.include_archived,
    }),
    queryFn: () =>
      api.get<PromptSummaryDTO[]>(`/prompts${qs ? `?${qs}` : ''}`),
  });
}

export function usePromptGroup(
  prompt_type: IPAPrompt | undefined,
  name: string | undefined,
) {
  return useQuery({
    queryKey:
      prompt_type && name
        ? promptKeys.group(prompt_type, name)
        : ['prompt', 'none'],
    queryFn: () =>
      api.get<PromptGroupDTO>(`/prompts/${prompt_type}/${name}`),
    enabled: !!(prompt_type && name),
  });
}

export function useEditPrompt(prompt_type: IPAPrompt, name: string) {
  const qc = useQueryClient();
  return useMutation({
    // The backend returns the full group (latest + history) so the
    // inline card can render without a follow-up fetch. Matches
    // archive_prompt's response shape.
    mutationFn: (body: EditPromptBody) =>
      api.post<PromptGroupDTO>(
        `/prompts/${prompt_type}/${name}/versions`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: promptKeys.all });
      qc.invalidateQueries({ queryKey: promptKeys.group(prompt_type, name) });
    },
  });
}

export function useArchivePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ prompt_type, name }: { prompt_type: IPAPrompt; name: string }) =>
      api.delete<PromptGroupDTO>(`/prompts/${prompt_type}/${name}`),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: promptKeys.all });
      qc.invalidateQueries({
        queryKey: promptKeys.group(vars.prompt_type, vars.name),
      });
    },
  });
}

/**
 * Stream a test run against a specific prompt version.
 *
 * Caller passes the full transcript each call (the test panel keeps it
 * in client state). `onEvent` receives `text_delta`, `error`, and
 * `done` events; the panel handles the appending UI itself.
 */
export function streamPromptTest(
  promptId: string,
  messages: TestPromptMessage[],
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return postStream({
    path: `/prompts/${promptId}/test`,
    body: { messages },
    onEvent,
    signal,
  });
}
