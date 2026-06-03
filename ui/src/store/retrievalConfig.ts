// Per-conversation RAG retrieval knobs for project chat: which modality and which
// optional stages are on. Persisted so a thread keeps its settings across reloads;
// sent with each project-chat turn. Mirrors the activeStreamIds pattern in store/ui.ts.

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { persist } from 'zustand/middleware';
import type { TurnRetrievalConfig } from '../types/generated';

export type RetrievalModality = NonNullable<TurnRetrievalConfig['modality']>;
export type RetrievalConfig = Required<TurnRetrievalConfig>;

// Full-quality default: PLUS modality with every stage on. PLUS falls back to SIMPLE
// server-side when a project has no LV document, so this is always a safe default.
export const DEFAULT_RETRIEVAL_CONFIG: RetrievalConfig = {
  modality: 'PLUS',
  multi_query: true,
  use_bm25: true,
  use_cross_encoder: true,
};

// LANGCHAIN is an agentic path that ignores the stage toggles; the UI disables them.
export const MODALITY_OPTIONS: RetrievalModality[] = ['SIMPLE', 'PLUS', 'LANGCHAIN'];

type RetrievalConfigState = {
  byConversation: Record<string, RetrievalConfig>;
};

type RetrievalConfigActions = {
  setConfig: (cid: string, patch: Partial<RetrievalConfig>) => void;
};

export const useRetrievalConfigStore = create<
  RetrievalConfigState & RetrievalConfigActions
>()(
  persist(
    immer((set) => ({
      byConversation: {},
      setConfig: (cid, patch) =>
        set((state) => {
          const current = state.byConversation[cid] ?? DEFAULT_RETRIEVAL_CONFIG;
          state.byConversation[cid] = { ...current, ...patch };
        }),
    })),
    { name: 'retrieval-config-store' },
  ),
);

// Stable reference when absent so selectors don't churn re-renders.
export function useRetrievalConfig(cid: string): RetrievalConfig {
  return useRetrievalConfigStore(
    (s) => s.byConversation[cid] ?? DEFAULT_RETRIEVAL_CONFIG,
  );
}
