// Query/mutation hooks for eval runs (the worker-executed grader queue). The
// list polls while any run is queued/running; events poll while a run is
// watched, so the Läufe tab shows live progress without SSE.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { EvalRun, EvalRunCreate, EvalRunEvent } from '../types/generated';

const ACTIVE_STATUSES: ReadonlyArray<EvalRun['status']> = ['queued', 'running'];

export function isActiveRun(run: EvalRun): boolean {
  return ACTIVE_STATUSES.includes(run.status);
}

export const evalRunKeys = {
  list: () => ['eval-runs'] as const,
  events: (uuid: string) => ['eval-runs', uuid, 'events'] as const,
};

// Unfiltered list (limit 50): a project's Läufe tab also shows project-free runs
// (chat_values), which grade the same prompts.
export function useEvalRuns() {
  return useQuery({
    queryKey: evalRunKeys.list(),
    queryFn: () => api.get<EvalRun[]>('/eval-runs'),
    refetchInterval: (query) =>
      (query.state.data ?? []).some(isActiveRun) ? 2500 : false,
  });
}

export function useEnqueueEvalRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EvalRunCreate) => api.post<EvalRun>('/eval-runs', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: evalRunKeys.list() });
    },
  });
}

export function useEvalRunEvents(uuid: string | null, live: boolean) {
  return useQuery({
    queryKey: uuid ? evalRunKeys.events(uuid) : ['eval-runs', 'none', 'events'],
    queryFn: () => api.get<EvalRunEvent[]>(`/eval-runs/${uuid}/events`),
    enabled: !!uuid,
    refetchInterval: live ? 2000 : false,
  });
}
