import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { APP_CONSTANTS } from '../appconstants';
import type {
  ExtractedPositionDTO,
  ModifyPositionBody,
  PositionDTO,
  PositionFieldsBody,
  PositionSummaryDTO,
} from '../types/generated';

export const positionKeys = {
  all: ['positions'] as const,
  detail: (id: string) => ['position', id] as const,
};

export function usePositions() {
  return useQuery({
    queryKey: positionKeys.all,
    queryFn: () => api.get<PositionSummaryDTO[]>('/positions'),
  });
}

export function usePosition(id: string | undefined) {
  return useQuery({
    queryKey: id ? positionKeys.detail(id) : ['position', 'none'],
    queryFn: () => api.get<PositionDTO>(`/positions/${id}`),
    enabled: !!id,
  });
}

export function useCreatePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PositionFieldsBody) =>
      api.post<PositionDTO>('/positions', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: positionKeys.all });
    },
  });
}

export function useModifyPosition(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ModifyPositionBody) =>
      api.patch<PositionDTO>(`/positions/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: positionKeys.all });
      qc.invalidateQueries({ queryKey: positionKeys.detail(id) });
    },
  });
}

export function useArchivePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<PositionDTO>(`/positions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: positionKeys.all });
    },
  });
}

/**
 * Extract structured position info from raw text the user pasted
 * (e.g. copied from a job board). Goes through the regular JSON API.
 */
export function extractPositionFromText(
  text: string,
): Promise<ExtractedPositionDTO> {
  return api.post<ExtractedPositionDTO>(
    '/extract/position-info/text',
    { text },
    APP_CONSTANTS.LLM_API_TIMEOUT_MS,
  );
}
