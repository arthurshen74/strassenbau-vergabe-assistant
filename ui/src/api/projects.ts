// Query/mutation hooks for projects + their documents.
//
// Document upload is multipart (a file or a flat ZIP), so it can't go through the
// JSON `api` client — it uses a raw fetch with FormData and lets the browser set
// the multipart boundary.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiBase } from './client';
import type { DocumentRead, ProjectCreate, ProjectRead } from '../types/generated';

export const projectKeys = {
  all: ['projects'] as const,
  list: () => [...projectKeys.all, 'list'] as const,
  detail: (uuid: string) => ['project', uuid] as const,
  documents: (uuid: string) => ['project', uuid, 'documents'] as const,
};

export function useProjects() {
  return useQuery({
    queryKey: projectKeys.list(),
    queryFn: () => api.get<ProjectRead[]>('/projects'),
  });
}

export function useProject(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? projectKeys.detail(uuid) : ['project', 'none'],
    queryFn: () => api.get<ProjectRead>(`/projects/${uuid}`),
    enabled: !!uuid,
  });
}

export function useProjectDocuments(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? projectKeys.documents(uuid) : ['project', 'none', 'documents'],
    queryFn: () => api.get<DocumentRead[]>(`/projects/${uuid}/documents`),
    enabled: !!uuid,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => api.post<ProjectRead>('/projects', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

async function postDocuments(
  projectUuid: string,
  files: File[],
  documentType: string,
): Promise<DocumentRead[]> {
  const form = new FormData();
  for (const f of files) form.append('files', f);
  form.append('document_type', documentType);
  // No Content-Type header: the browser sets the multipart boundary.
  const res = await fetch(`${apiBase}/projects/${projectUuid}/documents`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep the status
    }
    throw new Error(`Upload failed: ${detail}`);
  }
  return (await res.json()) as DocumentRead[];
}

export function useUploadDocuments(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ files, documentType }: { files: File[]; documentType: string }) =>
      postDocuments(projectUuid, files, documentType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: projectKeys.documents(projectUuid) });
    },
  });
}
