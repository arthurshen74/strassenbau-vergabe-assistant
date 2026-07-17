// Which component is rendered into the dispatcher's "main window".
//
// Opened from two unrelated places — the SSE handler deep in the chat hook
// (a dispatcher tool result) and a sidebar Command button — and closing it
// returns the conversation to full height without touching the URL. A shared
// store is the only thing both openers can reach cleanly; mirrors the
// activeStreamIds pattern in store/ui.ts. Transient, so it is not persisted.

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';

export type MainWindowKind =
  | 'prompts'
  | 'projects'
  | 'prompt_execution_log'
  | 'prompt_usage_log'
  | 'ingest_console'
  | 'katalog'
  | 'entity_rules'
  | 'ner_analysis';

export interface MainWindowView {
  kind: MainWindowKind;
  // Data carried when opened from a dispatcher tool result; absent when
  // opened from a sidebar command (the body fetches via REST instead).
  data?: unknown;
}

type MainWindowState = {
  view: MainWindowView | null;
};

type MainWindowActions = {
  openMainWindow: (view: MainWindowView) => void;
  closeMainWindow: () => void;
};

export const useMainWindowStore = create<MainWindowState & MainWindowActions>()(
  immer((set) => ({
    view: null,
    openMainWindow: (view) =>
      set((state) => {
        state.view = view;
      }),
    closeMainWindow: () =>
      set((state) => {
        state.view = null;
      }),
  })),
);

// Maps a dispatcher tool name to the main-window view it renders into.
// Tools absent from this map don't open a window.
const TOOL_VIEW_KIND: Record<string, MainWindowKind> = {
  view_prompts: 'prompts',
  view_projects: 'projects',
  view_prompt_execution_log: 'prompt_execution_log',
  view_prompt_usage_log: 'prompt_usage_log',
  view_ingest_console: 'ingest_console',
};

export function viewKindForTool(
  toolName: string | null | undefined,
): MainWindowKind | null {
  if (!toolName) return null;
  return TOOL_VIEW_KIND[toolName] ?? null;
}
