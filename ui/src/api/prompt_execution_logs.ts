// Query hooks for prompt execution logs.

import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type {
  PromptExecutionLogDetailDTO,
  PromptExecutionLogSummaryDTO,
} from '../types/generated';

export const promptLogKeys = {
  all: ['prompt-execution-logs'] as const,
  list: (limit?: number, offset?: number) =>
    [...promptLogKeys.all, { limit, offset }] as const,
  detail: (id: string) => ['prompt-execution-log', id] as const,
};

export function usePromptExecutionLogs(limit = 100, offset = 0) {
  return useQuery({
    queryKey: promptLogKeys.list(limit, offset),
    queryFn: () =>
      api.get<PromptExecutionLogSummaryDTO[]>(
        `/prompt-execution-logs?limit=${limit}&offset=${offset}`,
      ),
    // Refresh the list every 30 seconds so new entries appear automatically.
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

export function usePromptExecutionLog(id: string | undefined) {
  return useQuery({
    queryKey: id ? promptLogKeys.detail(id) : ['prompt-execution-log', 'none'],
    queryFn: () =>
      api.get<PromptExecutionLogDetailDTO>(`/prompt-execution-logs/${id}`),
    enabled: !!id,
    staleTime: Infinity, // Log entries are immutable; never re-fetch.
  });
}
