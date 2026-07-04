// Query/mutation hooks for RAG reference questions (the retrieval/answer gold set).
// Refs are validated server-side against the project's ingested documents; a
// question without refs is flagged refs_missing (answer grading only).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  RagGroundTruthRead,
  RagGroundTruthUpsert,
} from '../types/generated';

export const ragGroundTruthKeys = {
  list: (projectUuid: string) =>
    ['project', projectUuid, 'rag-ground-truth'] as const,
};

export function useRagGroundTruthList(projectUuid: string | undefined) {
  return useQuery({
    queryKey:
      projectUuid ?
        ragGroundTruthKeys.list(projectUuid)
      : ['project', 'none', 'rag-ground-truth'],
    queryFn: () =>
      api.get<RagGroundTruthRead[]>(`/projects/${projectUuid}/rag-ground-truth`),
    enabled: !!projectUuid,
  });
}

export function useCreateRagGroundTruth(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RagGroundTruthUpsert) =>
      api.post<RagGroundTruthRead>(
        `/projects/${projectUuid}/rag-ground-truth`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ragGroundTruthKeys.list(projectUuid) });
    },
  });
}

export function useUpdateRagGroundTruth(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      ragGroundTruthUuid,
      body,
    }: {
      ragGroundTruthUuid: string;
      body: RagGroundTruthUpsert;
    }) =>
      api.put<RagGroundTruthRead>(
        `/projects/${projectUuid}/rag-ground-truth/${ragGroundTruthUuid}`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ragGroundTruthKeys.list(projectUuid) });
    },
  });
}

export function useDeleteRagGroundTruth(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ragGroundTruthUuid: string) =>
      api.delete<void>(
        `/projects/${projectUuid}/rag-ground-truth/${ragGroundTruthUuid}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ragGroundTruthKeys.list(projectUuid) });
    },
  });
}
