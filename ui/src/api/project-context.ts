// Query/mutation hooks for a project's context globals (Baustelle/Deponie/strip dims/Fräsgut).
//
// The current view and version history are queries; an override (PUT) and a resolve (POST)
// are mutations that invalidate both so the panel reflects the new versions.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  ProjectContextHistory,
  ProjectContextRead,
  ProjectContextUpdate,
} from '../types/generated';

export const projectContextKeys = {
  context: (uuid: string) => ['project', uuid, 'context'] as const,
  history: (uuid: string) => ['project', uuid, 'context', 'history'] as const,
};

export function useProjectContext(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? projectContextKeys.context(uuid) : ['project', 'none', 'context'],
    queryFn: () => api.get<ProjectContextRead>(`/projects/${uuid}/context`),
    enabled: !!uuid,
  });
}

export function useProjectContextHistory(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? projectContextKeys.history(uuid) : ['project', 'none', 'context', 'history'],
    queryFn: () => api.get<ProjectContextHistory[]>(`/projects/${uuid}/context/history`),
    enabled: !!uuid,
  });
}

function invalidateContext(qc: ReturnType<typeof useQueryClient>, uuid: string) {
  qc.invalidateQueries({ queryKey: projectContextKeys.context(uuid) });
  qc.invalidateQueries({ queryKey: projectContextKeys.history(uuid) });
}

export function useUpdateProjectContext(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectContextUpdate) =>
      api.put<ProjectContextRead>(`/projects/${projectUuid}/context`, body),
    onSuccess: () => invalidateContext(qc, projectUuid),
  });
}

export function useResolveProjectContext(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<ProjectContextRead>(`/projects/${projectUuid}/context/resolve`),
    onSuccess: () => invalidateContext(qc, projectUuid),
  });
}
