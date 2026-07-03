// Katalog / recipe-author client bits. The recipe-author conversation reuses the generic
// conversation surface (prompt_type "rezept_autor") and the shared turn endpoint; its paused
// rezept_review interrupt is answered with a RezeptReviewDecision (posted as `{rezept_review}`).
//
// Phase 2 adds the catalog confirm-card server state: the bundle-state re-query and the
// activate/discard mutations the KatalogEntwurfCard drives.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import type {
  BundleBericht,
  BundleZustandAnsicht,
  ConversationRead,
} from '../types/generated';

const PROMPT_TYPE_REZEPT_AUTOR = 'rezept_autor';

export const katalogKeys = {
  bundle: (bundleUuid: string) => ['katalog', 'bundle', bundleUuid] as const,
};

// The current state of a draft bundle (re-queried on card mount/reload so a bundle long since
// activated or discarded renders truthfully instead of offering dead buttons).
export function useBundleZustand(bundleUuid: string | null) {
  return useQuery({
    queryKey: katalogKeys.bundle(bundleUuid ?? ''),
    queryFn: () => api.get<BundleZustandAnsicht>(`/katalog/bundle/${bundleUuid}`),
    enabled: !!bundleUuid,
  });
}

// Activate a draft bundle (the human confirm). Invalidates the bundle state so the card re-renders.
export function useBundleAktivieren() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (bundleUuid: string) =>
      api.post<BundleBericht>(`/katalog/bundle/${bundleUuid}/aktivieren`),
    onSettled: (_d, _e, bundleUuid) =>
      qc.invalidateQueries({ queryKey: katalogKeys.bundle(bundleUuid) }),
  });
}

// Discard a draft bundle. Invalidates the bundle state so the card re-renders.
export function useBundleVerwerfen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (bundleUuid: string) =>
      api.post<void>(`/katalog/bundle/${bundleUuid}/verwerfen`),
    onSettled: (_d, _e, bundleUuid) =>
      qc.invalidateQueries({ queryKey: katalogKeys.bundle(bundleUuid) }),
  });
}

// The reviewer's decision for a paused recipe-author run (mirrors the backend RezeptReviewDecision):
// `feedback` loops back to a redraft, `bestaetigt` persists the draft, `aktivieren` activates it.
export interface RezeptReviewDecision {
  bestaetigt: boolean;
  feedback: string | null;
  aktivieren: boolean;
}

// Launch a recipe-author conversation; the UI navigates to it and the estimator describes the recipe.
export function createRezeptAutorConversation(
  projectUuid: string | null,
): Promise<ConversationRead> {
  return api.post<ConversationRead>('/conversations', {
    prompt_type: PROMPT_TYPE_REZEPT_AUTOR,
    project_uuid: projectUuid,
    title: 'Neues Rezept',
  });
}
