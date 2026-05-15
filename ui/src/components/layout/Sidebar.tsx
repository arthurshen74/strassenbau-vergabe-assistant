// App-level sidebar. Shows the new-thread button at the top, the
// grouped conversation list in the middle, and a "View Log" button
// pinned to the bottom that opens the prompt-execution-log drawer.

import { ClipboardDocumentListIcon } from '@heroicons/react/20/solid';
import { useConversationList } from '../../api/conversations';
import { useUIStore } from '../../store/ui';
import { ConversationList } from './ConversationList';
import { NewThreadButton } from './NewThreadButton';

export function Sidebar() {
  const { data, isLoading, isError } = useConversationList();
  const openPromptLogDrawer = useUIStore((s) => s.openPromptLogDrawer);

  return (
    <aside className="flex h-full w-64 flex-col border-r border-zinc-950/5 bg-zinc-50 dark:border-white/5 dark:bg-zinc-950">
      <div className="border-b border-zinc-950/5 p-3 dark:border-white/5">
        <div className="mb-3 px-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Interview Prep
        </div>
        <NewThreadButton />
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {isLoading && (
          <div className="px-1 text-xs text-zinc-500">Loading…</div>
        )}
        {isError && (
          <div className="px-1 text-xs text-red-600 dark:text-red-400">
            Failed to load conversations.
          </div>
        )}
        {data && <ConversationList items={data} />}
      </div>

      {/* View Log button — pinned to the bottom of the sidebar */}
      <div className="border-t border-zinc-950/5 p-3 dark:border-white/5">
        <button
          type="button"
          onClick={openPromptLogDrawer}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
        >
          <ClipboardDocumentListIcon className="h-4 w-4 shrink-0" />
          View Prompt Log
        </button>
      </div>
    </aside>
  );
}
