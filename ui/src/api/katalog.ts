// Katalog confirm-card server state: the bundle-state re-query and the activate/discard
// mutations the KatalogEntwurfCard drives.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import type { BundleBericht, BundleZustandAnsicht } from '../types/generated';

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

