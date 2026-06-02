// Ephemeral UI state. Server state lives in TanStack Query — this is for
// view-shell concerns (sidebar collapsed, in-flight stream tracking) that
// don't belong in component state because multiple components read them.

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { persist } from 'zustand/middleware';

type UIState = {
  sidebarCollapsed: boolean;
  /**
   * conversation IDs that currently have an open SSE stream. Used to render
   * "thinking…" indicators in the sidebar / message list.
   */
  activeStreamIds: Record<string, boolean>;
};

type UIActions = {
  toggleSidebar: () => void;
  setStreamActive: (cid: string, active: boolean) => void;
};

type UIStore = UIState & UIActions;

export const useUIStore = create<UIStore>()(
  persist(
    immer((set) => ({
      sidebarCollapsed: false,
      activeStreamIds: {},

      toggleSidebar: () =>
        set((state) => {
          state.sidebarCollapsed = !state.sidebarCollapsed;
        }),

      setStreamActive: (cid, active) =>
        set((state) => {
          if (active) state.activeStreamIds[cid] = true;
          else delete state.activeStreamIds[cid];
        }),
    })),
    {
      name: 'ui-store',
      partialize: (state) => ({ sidebarCollapsed: state.sidebarCollapsed }),
    },
  ),
);
