// Query hooks for the project-info RAG queries. Versions are append-only per
// (query_key, language); publishing appends the next version and refetches the
// latest list and that key's history.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  RagQueryVersionCreate,
  RagQueryVersionRead,
} from '../types/generated';

export type RagQueryKey = RagQueryVersionRead['query_key'];

export const ragQueryKeys = {
  all: ['rag-queries'] as const,
  latest: (language: string) => [...ragQueryKeys.all, 'latest', language] as const,
  history: (key: RagQueryKey, language: string) =>
    [...ragQueryKeys.all, 'history', key, language] as const,
};

export function useRagQueries(language: string) {
  return useQuery({
    queryKey: ragQueryKeys.latest(language),
    queryFn: () =>
      api.get<RagQueryVersionRead[]>(
        `/rag-queries?language=${encodeURIComponent(language)}`,
      ),
  });
}

export function useRagQueryHistory(key: RagQueryKey, language: string) {
  return useQuery({
    queryKey: ragQueryKeys.history(key, language),
    queryFn: () =>
      api.get<RagQueryVersionRead[]>(
        `/rag-queries/${key}/history?language=${encodeURIComponent(language)}`,
      ),
  });
}

export function usePublishRagQuery(key: RagQueryKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RagQueryVersionCreate) =>
      api.post<RagQueryVersionRead>(`/rag-queries/${key}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ragQueryKeys.all }),
  });
}
