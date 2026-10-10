// Query/mutation hooks for projects + their documents.
//
// Document upload is multipart (a file or a flat ZIP), so it can't go through the
// JSON `api` client — it uses a raw fetch with FormData and lets the browser set
// the multipart boundary.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiBase } from './client';
import type {
  DocumentRead,
  IngestJobRead,
  LVItem,
  LVText,
  ProjectCreate,
  ProjectRead,
  ProjectUpdate,
} from '../types/generated';

export const projectKeys = {
  all: ['projects'] as const,
  list: () => [...projectKeys.all, 'list'] as const,
  detail: (uuid: string) => ['project', uuid] as const,
  documents: (uuid: string) => ['project', uuid, 'documents'] as const,
  lvItems: (uuid: string) => ['project', uuid, 'lv-items'] as const,
  lvTexts: (uuid: string) => ['project', uuid, 'lv-texts'] as const,
  lvItemSearch: (uuid: string, q: string) =>
    ['project', uuid, 'lv-items', 'search', q] as const,
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

export function useProjectLvItems(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? projectKeys.lvItems(uuid) : ['project', 'none', 'lv-items'],
    queryFn: () => api.get<LVItem[]>(`/projects/${uuid}/lv-items`),
    enabled: !!uuid,
  });
}

// The LV document's Vorbemerkungen, Hinweise and Nachtext in document order.
export function useProjectLvTexts(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? projectKeys.lvTexts(uuid) : ['project', 'none', 'lv-texts'],
    queryFn: () => api.get<LVText[]>(`/projects/${uuid}/lv-texts`),
    enabled: !!uuid,
  });
}

// Hybrid BM25/semantic search over the project's LV_ITEM chunks; enabled only once a query is
// submitted, so an empty box keeps the full list (useProjectLvItems) on screen.
export function useLvItemSearch(uuid: string, query: string) {
  return useQuery({
    queryKey: projectKeys.lvItemSearch(uuid, query),
    queryFn: () =>
      api.get<LVItem[]>(`/projects/${uuid}/lv-items/search?q=${encodeURIComponent(query)}`),
    enabled: query.length > 0,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => api.post<ProjectRead>('/projects', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

// Partial update of the project header fields; an explicit null clears a field.
export function useUpdateProject(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectUpdate) =>
      api.patch<ProjectRead>(`/projects/${projectUuid}`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: projectKeys.detail(projectUuid) });
      void qc.invalidateQueries({ queryKey: projectKeys.list() });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectUuid: string) => api.delete<void>(`/projects/${projectUuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

async function postDocuments(projectUuid: string, files: File[]): Promise<DocumentRead[]> {
  const form = new FormData();
  for (const f of files) form.append('files', f);
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

export function useIngestDocument(projectUuid: string) {
  // Queues a (re-)ingest; progress is reflected by the project's ingest status stream, so there's
  // nothing to invalidate here.
  return useMutation({
    mutationFn: (documentUuid: string) =>
      api.post<IngestJobRead>(`/projects/${projectUuid}/documents/${documentUuid}/ingest`),
  });
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
    // The server derives each document's type from its filename (GAEB .d83/.x83 -> LV,
    // everything else -> prose), so the whole batch goes in one request.
    mutationFn: (files: File[]) => postDocuments(projectUuid, files),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: projectKeys.documents(projectUuid) });
    },
  });
}
