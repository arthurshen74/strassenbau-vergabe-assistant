// Query hooks for the document detail view: header metadata, a page of chunks (Simple or
// LangChain, with source-doc-type filter + text search), a form's extracted fields, and
// the ingestion activity log.

import { useQuery } from '@tanstack/react-query';

import { api } from './client';
import type {
  ActivityListRead,
  ChunkListRead,
  ContextChunk,
  DocumentDetailRead,
  FormFieldRead,
} from '../types/generated';

export type SourceDocType = ContextChunk['source_doc_type'];

export interface ChunkFilters {
  source: 'simple' | 'langchain';
  doc_type?: SourceDocType;
  q?: string;
  offset?: number;
  limit?: number;
  [key: string]: string | number | undefined;
}

function queryString(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const documentKeys = {
  detail: (p: string, d: string) => ['document-detail', p, d] as const,
  chunks: (p: string, d: string, f: ChunkFilters) => ['document-chunks', p, d, f] as const,
  activity: (p: string, d: string, offset: number) =>
    ['document-activity', p, d, offset] as const,
  formFields: (p: string, d: string) => ['document-form-fields', p, d] as const,
};

export function useDocumentDetail(projectUuid: string, documentUuid: string | undefined) {
  return useQuery({
    queryKey: documentKeys.detail(projectUuid, documentUuid ?? 'none'),
    queryFn: () =>
      api.get<DocumentDetailRead>(
        `/projects/${projectUuid}/documents/${documentUuid}/detail`,
      ),
    enabled: !!documentUuid,
  });
}

export function useDocumentChunks(
  projectUuid: string,
  documentUuid: string | undefined,
  filters: ChunkFilters,
) {
  return useQuery({
    queryKey: documentKeys.chunks(projectUuid, documentUuid ?? 'none', filters),
    queryFn: () =>
      api.get<ChunkListRead>(
        `/projects/${projectUuid}/documents/${documentUuid}/chunks${queryString(filters)}`,
      ),
    enabled: !!documentUuid,
  });
}

export function useDocumentActivity(
  projectUuid: string,
  documentUuid: string | undefined,
  offset: number,
  limit: number,
) {
  return useQuery({
    queryKey: documentKeys.activity(projectUuid, documentUuid ?? 'none', offset),
    queryFn: () =>
      api.get<ActivityListRead>(
        `/projects/${projectUuid}/documents/${documentUuid}/activity${queryString({ offset, limit })}`,
      ),
    enabled: !!documentUuid,
  });
}

export function useDocumentFormFields(projectUuid: string, documentUuid: string | undefined) {
  return useQuery({
    queryKey: documentKeys.formFields(projectUuid, documentUuid ?? 'none'),
    queryFn: () =>
      api.get<FormFieldRead[]>(
        `/projects/${projectUuid}/documents/${documentUuid}/form-fields`,
      ),
    enabled: !!documentUuid,
  });
}
