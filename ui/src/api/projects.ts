// Query/mutation hooks for projects + their documents.
//
// Document upload and ZIP-first project creation are multipart, so they can't go through the
// JSON `api` client — they use a raw fetch with FormData and let the browser set the
// multipart boundary.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api, apiBase } from './client';
import type {
  DocumentRead,
  IngestJobRead,
  LVItem,
  LVText,
  ProjectCreate,
  ProjectFromZipResult,
  ProjectInfoJobRead,
  ProjectInfoRunRequest,
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
  projectInfo: (uuid: string) => ['project', uuid, 'project-info'] as const,
  lvItemSearch: (uuid: string, q: string) =>
    ['project', uuid, 'lv-items', 'search', q] as const,
  // Under the documents prefix, so invalidating a project's documents refetches these too.
  documentLvItems: (uuid: string, documentUuid: string) =>
    ['project', uuid, 'documents', documentUuid, 'lv-items'] as const,
  documentLvTexts: (uuid: string, documentUuid: string) =>
    ['project', uuid, 'documents', documentUuid, 'lv-texts'] as const,
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

// Every LV document's Vorbemerkungen, Hinweise and Nachtext in document order.
export function useProjectLvTexts(uuid: string | undefined) {
  return useQuery({
    queryKey: uuid ? projectKeys.lvTexts(uuid) : ['project', 'none', 'lv-texts'],
    queryFn: () => api.get<LVText[]>(`/projects/${uuid}/lv-texts`),
    enabled: !!uuid,
  });
}

// One LV document's positions ordered by oz.
export function useDocumentLvItems(projectUuid: string, documentUuid: string | undefined) {
  return useQuery({
    queryKey: documentUuid
      ? projectKeys.documentLvItems(projectUuid, documentUuid)
      : ['project', projectUuid, 'documents', 'none', 'lv-items'],
    queryFn: () =>
      api.get<LVItem[]>(`/projects/${projectUuid}/documents/${documentUuid}/lv-items`),
    enabled: !!documentUuid,
  });
}

// One LV document's Vorbemerkungen, Hinweise and Nachtext in document order.
export function useDocumentLvTexts(projectUuid: string, documentUuid: string | undefined) {
  return useQuery({
    queryKey: documentUuid
      ? projectKeys.documentLvTexts(projectUuid, documentUuid)
      : ['project', projectUuid, 'documents', 'none', 'lv-texts'],
    queryFn: () =>
      api.get<LVText[]>(`/projects/${projectUuid}/documents/${documentUuid}/lv-texts`),
    enabled: !!documentUuid,
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

const PROJECT_INFO_POLL_MS = 3000;
const OPEN_PROJECT_INFO_STATUSES: ReadonlyArray<ProjectInfoJobRead['status']> = [
  'queued',
  'running',
];

export function isProjectInfoOpen(job: ProjectInfoJobRead | null | undefined): boolean {
  return !!job && OPEN_PROJECT_INFO_STATUSES.includes(job.status);
}

// The project's latest Projektinfo job, or null when it never had one. Polls while the job is
// queued or running; when a poll sees it finish, the project is refetched so the header shows
// the written fields.
export function useProjectInfo(projectUuid: string) {
  const qc = useQueryClient();
  const key = projectKeys.projectInfo(projectUuid);
  return useQuery({
    queryKey: key,
    queryFn: async () => {
      let job: ProjectInfoJobRead;
      try {
        job = await api.get<ProjectInfoJobRead>(`/projects/${projectUuid}/project-info`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
      const previous = qc.getQueryData<ProjectInfoJobRead | null>(key);
      if (isProjectInfoOpen(previous) && job.status === 'done') {
        void qc.invalidateQueries({ queryKey: projectKeys.detail(projectUuid), exact: true });
        void qc.invalidateQueries({ queryKey: projectKeys.list() });
      }
      return job;
    },
    refetchInterval: (query) =>
      isProjectInfoOpen(query.state.data) ? PROJECT_INFO_POLL_MS : false,
  });
}

// Queues a Projektinfo run; the server returns the open job instead when one is pending.
export function useRunProjectInfo(projectUuid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectInfoRunRequest) =>
      api.post<ProjectInfoJobRead>(`/projects/${projectUuid}/project-info/run`, body),
    onSuccess: (job) => qc.setQueryData(projectKeys.projectInfo(projectUuid), job),
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

async function postProjectZip(file: File): Promise<ProjectFromZipResult> {
  const form = new FormData();
  form.append('file', file);
  // No Content-Type header: the browser sets the multipart boundary.
  const res = await fetch(`${apiBase}/projects/from-zip`, { method: 'POST', body: form });
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
  return (await res.json()) as ProjectFromZipResult;
}

// Creates a project named after the ZIP and queues every PDF/GAEB file inside it (nested ZIPs
// included); entries that were not ingested come back in `skipped`.
export function useCreateProjectFromZip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postProjectZip,
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
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
    // The server derives each document's type from its filename (each GAEB .d83/.x83 -> a
    // new LV document, everything else -> prose), so the whole batch goes in one request.
    mutationFn: (files: File[]) => postDocuments(projectUuid, files),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: projectKeys.documents(projectUuid) });
    },
  });
}
