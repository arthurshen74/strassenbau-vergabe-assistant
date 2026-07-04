// Open conversation tabs for the workspace tab strip, in open order. The URL
// (/c/:id) stays the source of truth for the *active* tab; this store only
// tracks which conversations are open. TabStrip syncs URL -> store, so any
// navigation to a conversation opens its tab.

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { persist } from 'zustand/middleware';

// Hard cap on open tabs; opening one more evicts the oldest other tab.
export const MAX_OPEN_TABS = 6;

type TabsState = {
  openTabs: string[];
};

type TabsActions = {
  openTab: (cid: string) => void;
  closeTab: (cid: string) => void;
  /** Drop tabs whose conversation no longer exists (deleted here or elsewhere). */
  pruneTabs: (existingIds: string[]) => void;
};

export const useTabsStore = create<TabsState & TabsActions>()(
  persist(
    immer((set) => ({
      openTabs: [],

      openTab: (cid) =>
        set((s) => {
          if (s.openTabs.includes(cid)) return;
          s.openTabs.push(cid);
          if (s.openTabs.length > MAX_OPEN_TABS) {
            const evict = s.openTabs.find((t) => t !== cid);
            if (evict) s.openTabs.splice(s.openTabs.indexOf(evict), 1);
          }
        }),

      closeTab: (cid) =>
        set((s) => {
          s.openTabs = s.openTabs.filter((t) => t !== cid);
        }),

      pruneTabs: (existingIds) =>
        set((s) => {
          if (s.openTabs.some((t) => !existingIds.includes(t))) {
            s.openTabs = s.openTabs.filter((t) => existingIds.includes(t));
          }
        }),
    })),
    { name: 'tabs-store' },
  ),
);

// The tab to activate when `cid` closes: right neighbour, else left, else none.
export function neighborTab(openTabs: string[], cid: string): string | null {
  const i = openTabs.indexOf(cid);
  if (i === -1) return null;
  return openTabs[i + 1] ?? openTabs[i - 1] ?? null;
}
