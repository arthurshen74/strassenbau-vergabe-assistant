// Dispatcher metadata. Today this is just the slash-command catalog
// the workspace ChatInput uses for autocomplete. The catalog is small
// and changes only with deployments, so we cache aggressively (no
// staleness window worth tuning) and fall back to an empty list while
// loading — the input is still fully functional without autocomplete.

import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { SlashCommandSpec } from '../lib/slash-commands';

export const dispatcherKeys = {
  slashCommands: ['dispatcher', 'slash-commands'] as const,
};

interface SlashCommandRow {
  name: string;
  description: string;
}

export function useSlashCommands(): SlashCommandSpec[] {
  const { data } = useQuery({
    queryKey: dispatcherKeys.slashCommands,
    queryFn: () =>
      api.get<SlashCommandRow[]>('/dispatcher/slash-commands'),
    // Catalog is deploy-stable; no need to refetch on focus etc.
    staleTime: Infinity,
  });
  return data ?? [];
}
