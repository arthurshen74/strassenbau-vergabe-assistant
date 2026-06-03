// Query hooks for prompts. The ViewPrompts command fetches the latest
// version of each prompt type via GET /prompts; the dispatcher's
// `view_prompts` tool returns the same shape, so PromptList renders both.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { PromptVersionCreate, PromptVersionRead } from '../types/generated';

export const promptKeys = {
  all: ['prompts'] as const,
  latest: () => [...promptKeys.all, 'latest'] as const,
};

export function usePromptsLatest() {
  return useQuery({
    queryKey: promptKeys.latest(),
    queryFn: () => api.get<PromptVersionRead[]>('/prompts'),
  });
}

// Append a new prompt version. Versions are immutable and append-only, so the
// created version (highest number) is automatically the active one.
export function useCreatePromptVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PromptVersionCreate) =>
      api.post<PromptVersionRead>('/prompts', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: promptKeys.all });
    },
  });
}
