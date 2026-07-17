// Query/mutation hooks for NER error flags: capture a misprediction (create runs
// the one-shot LLM analysis server-side), browse/filter, resolve/override, retry a
// failed analysis, delete. Mutations invalidate the list and the dashboard summary.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  NerFlag,
  NerFlagSummary,
  NerFlagUpdate,
  NewNerFlag,
} from '../types/generated';

export type NerFlagKind = NerFlag['kind'];
export type NerFailureCategory = NonNullable<NerFlag['category']>;
export type NerFlagStatus = NerFlag['status'];

export interface NerFlagFilters {
  kind?: NerFlagKind;
  category?: NerFailureCategory;
  status?: NerFlagStatus;
}

export const nerFlagKeys = {
  all: ['ner-flags'] as const,
  list: (filters: NerFlagFilters) => [...nerFlagKeys.all, 'list', filters] as const,
  summary: () => [...nerFlagKeys.all, 'summary'] as const,
};

function queryString(filters: NerFlagFilters): string {
  const params = new URLSearchParams();
  if (filters.kind) params.set('kind', filters.kind);
  if (filters.category) params.set('category', filters.category);
  if (filters.status) params.set('status', filters.status);
  const query = params.toString();
  return query ? `?${query}` : '';
}

export function useNerFlags(filters: NerFlagFilters = {}) {
  return useQuery({
    queryKey: nerFlagKeys.list(filters),
    queryFn: () => api.get<NerFlag[]>(`/ner-flags${queryString(filters)}`),
  });
}

export function useNerFlagSummary() {
  return useQuery({
    queryKey: nerFlagKeys.summary(),
    queryFn: () => api.get<NerFlagSummary>('/ner-flags/summary'),
  });
}

export function useCreateNerFlag() {
  const qc = useQueryClient();
  return useMutation({
    // The analysis LLM call runs inside create; allow a generous timeout.
    mutationFn: (body: NewNerFlag) => api.post<NerFlag>('/ner-flags', body, 120_000),
    onSuccess: () => qc.invalidateQueries({ queryKey: nerFlagKeys.all }),
  });
}

export function useUpdateNerFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: NerFlagUpdate }) =>
      api.patch<NerFlag>(`/ner-flags/${uuid}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: nerFlagKeys.all }),
  });
}

export function useRetryNerFlagAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<NerFlag>(`/ner-flags/${uuid}/analyze`, undefined, 120_000),
    onSuccess: () => qc.invalidateQueries({ queryKey: nerFlagKeys.all }),
  });
}

export function useDeleteNerFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete<void>(`/ner-flags/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: nerFlagKeys.all }),
  });
}

// Effective category: the user override wins over the LLM assignment (mirrors the
// server-side computed field used by the summary aggregation).
export function effectiveCategory(flag: NerFlag): NerFailureCategory | null {
  return flag.category_override ?? flag.category ?? null;
}
