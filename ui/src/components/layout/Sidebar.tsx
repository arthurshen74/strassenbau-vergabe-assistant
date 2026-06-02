// App-level sidebar:
//   - Commands: open a component into the dispatcher's main window
//   - Conversations: dispatcher threads
//   - Project Conversations: project-chat threads
//
// The single GET /conversations list is split by prompt_type here — purely a
// presentation choice for this surface.

import {
  ChartBarIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
  FolderIcon,
} from '@heroicons/react/20/solid';
import {
  PROMPT_TYPE_DISPATCHER,
  PROMPT_TYPE_PROJECT_CHAT,
  useConversationList,
} from '../../api/conversations';
import { useMainWindowStore, type MainWindowKind } from '../../store/mainWindow';
import { ConversationList } from './ConversationList';
import { NewThreadButton } from './NewThreadButton';

type CommandIcon = typeof DocumentTextIcon;

const COMMANDS: { label: string; kind: MainWindowKind; Icon: CommandIcon }[] = [
  { label: 'View Prompts', kind: 'prompts', Icon: DocumentTextIcon },
  { label: 'View Project', kind: 'projects', Icon: FolderIcon },
  {
    label: 'View Prompt Execution Log',
    kind: 'prompt_execution_log',
    Icon: ClipboardDocumentListIcon,
  },
  {
    label: 'View Prompt Usage Log',
    kind: 'prompt_usage_log',
    Icon: ChartBarIcon,
  },
];

const SECTION_LABEL =
  'px-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400';

export function Sidebar() {
  const { data, isLoading, isError } = useConversationList();
  const openMainWindow = useMainWindowStore((s) => s.openMainWindow);

  const all = data ?? [];
  const dispatcherConvos = all.filter(
    (c) => c.prompt_type === PROMPT_TYPE_DISPATCHER,
  );
  const projectConvos = all.filter(
    (c) => c.prompt_type === PROMPT_TYPE_PROJECT_CHAT,
  );

  return (
    <aside className="flex h-full w-64 flex-col border-r border-zinc-950/5 bg-zinc-50 dark:border-white/5 dark:bg-zinc-950">
      <div className="border-b border-zinc-950/5 p-3 dark:border-white/5">
        <div className="mb-3 px-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Roadbuilders Assistant
        </div>
        <NewThreadButton />
      </div>

      <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-3">
        <div className="flex flex-col gap-1">
          <div className={SECTION_LABEL}>Commands</div>
          {COMMANDS.map(({ label, kind, Icon }) => (
            <button
              key={kind}
              type="button"
              onClick={() => openMainWindow({ kind })}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-zinc-700 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <Icon className="h-4 w-4 shrink-0 text-zinc-400" />
              {label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-1">
          <div className={SECTION_LABEL}>Conversations</div>
          {isLoading && (
            <div className="px-1 text-xs text-zinc-500">Loading…</div>
          )}
          {isError && (
            <div className="px-1 text-xs text-red-600 dark:text-red-400">
              Failed to load conversations.
            </div>
          )}
          {!isLoading && !isError && (
            <ConversationList
              items={dispatcherConvos}
              emptyHint="No conversations yet."
            />
          )}
        </div>

        <div className="flex flex-col gap-1">
          <div className={SECTION_LABEL}>Project Conversations</div>
          {!isLoading && !isError && (
            <ConversationList
              items={projectConvos}
              emptyHint="No project conversations yet."
            />
          )}
        </div>
      </div>
    </aside>
  );
}
