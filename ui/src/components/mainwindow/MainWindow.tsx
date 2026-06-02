// The dispatcher's main window: fills the conversation area above the chat
// input, with a close "X" that returns the conversation to full height.
// Body components take an optional `data` prop — present when opened from a
// dispatcher tool result, absent when opened from a sidebar command (the body
// then fetches via REST). Same component, two triggers.

import { XMarkIcon } from '@heroicons/react/20/solid';
import { useMainWindowStore, type MainWindowView } from '../../store/mainWindow';
import { PromptList } from '../../views/workspace/tools/PromptList';
import { EmptyState } from '../feedback/EmptyState';

const TITLES: Record<MainWindowView['kind'], string> = {
  prompts: 'Prompts',
  projects: 'Projects',
  prompt_execution_log: 'Prompt Execution Log',
  prompt_usage_log: 'Prompt Usage Log',
};

export function MainWindow({ view }: { view: MainWindowView }) {
  const closeMainWindow = useMainWindowStore((s) => s.closeMainWindow);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-950/5 px-4 dark:border-white/5">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {TITLES[view.kind]}
        </div>
        <button
          type="button"
          onClick={closeMainWindow}
          aria-label="Close"
          className="rounded-md p-1 text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <MainWindowBody view={view} />
      </div>
    </div>
  );
}

function MainWindowBody({ view }: { view: MainWindowView }) {
  switch (view.kind) {
    case 'prompts':
      return <PromptList data={view.data} />;
    case 'projects':
    case 'prompt_execution_log':
    case 'prompt_usage_log':
      return (
        <EmptyState title={TITLES[view.kind]} description="Coming soon." />
      );
    default: {
      const _exhaustive: never = view.kind;
      void _exhaustive;
      return null;
    }
  }
}
