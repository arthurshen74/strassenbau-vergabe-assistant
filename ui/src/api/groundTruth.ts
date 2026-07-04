// Query/mutation hooks for calculation ground truth (the curated gold set).
// Rows come back with staleness info against the current recipe worklist; the
// union of a row's gold variable names and its missing_variables is the full
// worklist, which is what the editor's add-variable picker offers.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { GroundTruthRead, GroundTruthUpsert } from '../types/generated';

export const groundTruthKeys = {
  list: (projectUuid: string) =>
    ['project', projectUuid, 'ground-truth'] as const,
};

export function useGroundTruthList(projectUuid: string | undefined) {
  return useQuery({
    queryKey:
      projectUuid ?
        groundTruthKeys.list(projectUuid)
      : ['project', 'none', 'ground-truth'],
    queryFn: () =>
      api.get<GroundTruthRead[]>(`/projects/${projectUuid}/ground-truth`),
    enabled: !!projectUuid,
  });
}

export function useUpsertGroundTruth(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      lvItemUuid,
      body,
    }: {
      lvItemUuid: string;
      body: GroundTruthUpsert;
    }) =>
      api.put<GroundTruthRead>(
        `/projects/${projectUuid}/ground-truth/${lvItemUuid}`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: groundTruthKeys.list(projectUuid) });
    },
  });
}

export function useDeleteGroundTruth(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lvItemUuid: string) =>
      api.delete<void>(`/projects/${projectUuid}/ground-truth/${lvItemUuid}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: groundTruthKeys.list(projectUuid) });
    },
  });
}
