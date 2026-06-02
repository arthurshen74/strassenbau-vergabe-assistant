// Query/mutation hooks for projects + their documents.
//
// Document upload is multipart (a file or a flat ZIP), so it can't go through the
// JSON `api` client — it uses a raw fetch with FormData and lets the browser set
// the multipart boundary.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiBase } from './client';
import type { DocumentRead, ProjectCreate, ProjectRead } from '../types/generated';
import {
  DOCUMENT_TYPE_LV,
  DOCUMENT_TYPE_PROSE,
  classifyDocumentType,
  type DocumentType,
} from '../lib/documentType';

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
  documentType: DocumentType,
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

export function useDeleteDocument(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentUuid: string) =>
      api.delete<void>(`/projects/${projectUuid}/documents/${documentUuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.documents(projectUuid) }),
  });
}

export function useUploadDocuments(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (files: File[]) => {
      // The type is derived from each filename. The endpoint applies one
      // document_type to the whole batch, so prose and LV files are sent as
      // separate requests. Prose goes first so an LV conflict can't block it.
      const groups: Record<DocumentType, File[]> = {
        [DOCUMENT_TYPE_PROSE]: [],
        [DOCUMENT_TYPE_LV]: [],
      };
      for (const f of files) groups[classifyDocumentType(f.name)].push(f);

      const created: DocumentRead[] = [];
      for (const documentType of [DOCUMENT_TYPE_PROSE, DOCUMENT_TYPE_LV] as const) {
        const group = groups[documentType];
        if (group.length > 0) {
          created.push(...(await postDocuments(projectUuid, group, documentType)));
        }
      }
      return created;
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: projectKeys.documents(projectUuid) });
    },
  });
}
