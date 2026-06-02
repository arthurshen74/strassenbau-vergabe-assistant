// Query hooks for prompts. The ViewPrompts command fetches the latest
// version of each prompt type via GET /prompts; the dispatcher's
// `view_prompts` tool returns the same shape, so PromptList renders both.

import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { PromptVersionRead } from '../types/generated';

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
