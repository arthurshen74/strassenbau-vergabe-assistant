// Katalog confirm-card server state: the bundle-state re-query and the activate/discard
// mutations the KatalogEntwurfCard drives.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import type {
  BundleBericht,
  BundleZustandAnsicht,
  KatalogZeile,
} from '../types/generated';

// The catalog entities the workspace Katalog view browses (the three §5 tabs, plus what a
// definitions detail links to). Values are the KatalogEntitaet enum strings (the route path).
export type KatalogEntitaet =
  | 'globale_variablen'
  | 'variablen'
  | 'formeln';

export const katalogKeys = {
  bundle: (bundleUuid: string) => ['katalog', 'bundle', bundleUuid] as const,
  aktive: (entitaet: string) => ['katalog', 'aktive', entitaet] as const,
  versionen: (entitaet: string, schluessel: string) =>
    ['katalog', 'versionen', entitaet, schluessel] as const,
};

// The active rows of one catalog entity (envelope form; payload rendered by entity kind).
export function useKatalogAktive(entitaet: KatalogEntitaet) {
  return useQuery({
    queryKey: katalogKeys.aktive(entitaet),
    queryFn: () => api.get<KatalogZeile[]>(`/katalog/${entitaet}`),
  });
}

// Every version of one entry (SCD-2 timeline), oldest first — the Versionshistorie.
export function useKatalogVersionen(
  entitaet: KatalogEntitaet,
  schluessel: string | null,
) {
  return useQuery({
    queryKey: katalogKeys.versionen(entitaet, schluessel ?? ''),
    queryFn: () =>
      api.get<KatalogZeile[]>(`/katalog/${entitaet}/${schluessel}/versionen`),
    enabled: !!schluessel,
  });
}

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

