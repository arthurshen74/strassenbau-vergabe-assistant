// Query hooks for the prompt execution log and OpenRouter usage log. Filters
// (prompt_type/operation + date range) and paging (limit/offset) are server-side
// query params.

import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type {
  OpenRouterUsageRead,
  PromptExecutionLogRead,
  PromptExecutionLogSummary,
} from '../types/generated';

export interface ExecutionLogFilters {
  prompt_type?: string;
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | undefined;
}

export interface UsageFilters {
  operation?: string;
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | undefined;
}

function queryString(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const logKeys = {
  execution: (f: ExecutionLogFilters) => ['execution-logs', f] as const,
  executionDetail: (uuid: string) => ['execution-log', uuid] as const,
  usage: (f: UsageFilters) => ['usage-logs', f] as const,
};

export function usePromptExecutionLogs(filters: ExecutionLogFilters) {
  return useQuery({
    queryKey: logKeys.execution(filters),
    queryFn: () =>
      api.get<PromptExecutionLogSummary[]>(`/prompt-execution-logs${queryString(filters)}`),
  });
}

export function usePromptExecutionLog(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? logKeys.executionDetail(uuid) : ['execution-log', 'none'],
    queryFn: () => api.get<PromptExecutionLogRead>(`/prompt-execution-logs/${uuid}`),
    enabled: !!uuid,
  });
}

export function useUsageLogs(filters: UsageFilters) {
  return useQuery({
    queryKey: logKeys.usage(filters),
    queryFn: () => api.get<OpenRouterUsageRead[]>(`/usage${queryString(filters)}`),
  });
}
