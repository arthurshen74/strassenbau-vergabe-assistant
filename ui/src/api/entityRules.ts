// Query/mutation hooks for the Entity Rules admin page. Rules feed the DB-backed
// spaCy EntityRuler; mutations invalidate the list (and labels, whose distinct set
// can shift) so the table and the label autocomplete stay current.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  EntityRuleCreate,
  EntityRuleRead,
  EntityRuleUpdate,
} from '../types/generated';

export const entityRuleKeys = {
  all: ['entity-rules'] as const,
  list: () => [...entityRuleKeys.all, 'list'] as const,
  labels: () => [...entityRuleKeys.all, 'labels'] as const,
};

export function useEntityRules() {
  return useQuery({
    queryKey: entityRuleKeys.list(),
    queryFn: () => api.get<EntityRuleRead[]>('/entity-rules'),
  });
}

export function useEntityRuleLabels() {
  return useQuery({
    queryKey: entityRuleKeys.labels(),
    queryFn: () => api.get<string[]>('/entity-rules/labels'),
  });
}

export function useCreateEntityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EntityRuleCreate) =>
      api.post<EntityRuleRead>('/entity-rules', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityRuleKeys.all }),
  });
}

export function useUpdateEntityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: EntityRuleUpdate }) =>
      api.patch<EntityRuleRead>(`/entity-rules/${uuid}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityRuleKeys.all }),
  });
}

export function useDeleteEntityRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete<void>(`/entity-rules/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityRuleKeys.all }),
  });
}
