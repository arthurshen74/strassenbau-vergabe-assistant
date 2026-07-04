// Query hooks for Gate-B variable corrections (read-only error-analysis telemetry;
// corrections are only ever written by the EKT Gate-B flow).

import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type {
  CorrectionSummaryRow,
  VariableCorrection,
} from '../types/generated';

// Reasons that count against extraction accuracy; the rest are data gaps or expert preference.
export const MODEL_ERROR_REASONS: ReadonlyArray<VariableCorrection['reason']> = [
  'falscher_wert',
  'falsche_quelle',
  'einheit',
];

// The four analysis buckets a correction reason falls into (drives chart/badge colors).
export type ReasonKind = 'model' | 'gap' | 'preference' | 'other';

export function reasonKind(reason: VariableCorrection['reason']): ReasonKind {
  if (reason != null && MODEL_ERROR_REASONS.includes(reason)) return 'model';
  if (reason === 'kontext_fehlt') return 'gap';
  if (reason === 'kalkulator_ermessen') return 'preference';
  return 'other';
}

export interface CorrectionFilters {
  variableName?: string;
  reason?: string;
}

export const correctionKeys = {
  list: (projectUuid: string, filters: CorrectionFilters) =>
    ['project', projectUuid, 'corrections', filters] as const,
  summary: (projectUuid: string) =>
    ['project', projectUuid, 'corrections', 'summary'] as const,
};

export function useCorrections(
  projectUuid: string | undefined,
  filters: CorrectionFilters = {},
) {
  const params = new URLSearchParams();
  if (filters.variableName) params.set('variable_name', filters.variableName);
  if (filters.reason) params.set('reason', filters.reason);
  const qs = params.toString();
  return useQuery({
    queryKey:
      projectUuid ?
        correctionKeys.list(projectUuid, filters)
      : ['project', 'none', 'corrections', filters],
    queryFn: () =>
      api.get<VariableCorrection[]>(
        `/projects/${projectUuid}/corrections${qs ? `?${qs}` : ''}`,
      ),
    enabled: !!projectUuid,
  });
}

export function useCorrectionsSummary(projectUuid: string | undefined) {
  return useQuery({
    queryKey:
      projectUuid ?
        correctionKeys.summary(projectUuid)
      : ['project', 'none', 'corrections', 'summary'],
    queryFn: () =>
      api.get<CorrectionSummaryRow[]>(
        `/projects/${projectUuid}/corrections/summary`,
      ),
    enabled: !!projectUuid,
  });
}
