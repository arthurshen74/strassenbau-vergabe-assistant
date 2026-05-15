// In-progress chat input per conversation. Persisted so that navigating
// away and back preserves what the user was typing. Keyed by conversation
// id (or "new" for the unsubmitted-thread input).

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { persist } from 'zustand/middleware';

type DraftsState = {
  drafts: Record<string, string>;
};

type DraftsActions = {
  setDraft: (key: string, value: string) => void;
  clearDraft: (key: string) => void;
};

export const useDraftsStore = create<DraftsState & DraftsActions>()(
  persist(
    immer((set) => ({
      drafts: {},
      setDraft: (key, value) =>
        set((s) => {
          if (value) s.drafts[key] = value;
          else delete s.drafts[key];
        }),
      clearDraft: (key) =>
        set((s) => {
          delete s.drafts[key];
        }),
    })),
    { name: 'drafts-store' },
  ),
);
