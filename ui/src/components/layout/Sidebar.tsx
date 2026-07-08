// App-level sidebar:
//   - a single-shot dispatcher command bar
//   - Commands: open a component into the global main window
//   - Project Conversations: project-chat threads (the only persistent conversations)

import { Link } from 'react-router-dom';
import {
  BookOpenIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  CommandLineIcon,
  DocumentTextIcon,
  FolderIcon,
} from '@heroicons/react/20/solid';
import {
  PROMPT_TYPE_EKT_CALCULATOR,
  PROMPT_TYPE_KATALOG_CHAT,
  PROMPT_TYPE_PROJECT_CHAT,
  useConversationList,
} from '../../api/conversations';
import { useStartKatalogChat } from '../../views/main/useStartKatalogChat';
import { useMainWindowStore, type MainWindowKind } from '../../store/mainWindow';
import { ConversationList } from './ConversationList';

type CommandIcon = typeof DocumentTextIcon;

const COMMANDS: { label: string; kind: MainWindowKind; Icon: CommandIcon }[] = [
  { label: 'View Project', kind: 'projects', Icon: FolderIcon },
  {
    label: 'Ingest Console',
    kind: 'ingest_console',
    Icon: CommandLineIcon,
  },
  { label: 'View Prompts', kind: 'prompts', Icon: DocumentTextIcon },
  { label: 'View Katalog', kind: 'katalog', Icon: BookOpenIcon },
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
  const startKatalogChat = useStartKatalogChat();

  const all = data ?? [];
  const projectConvos = all.filter(
    (c) =>
      c.prompt_type === PROMPT_TYPE_PROJECT_CHAT ||
      c.prompt_type === PROMPT_TYPE_EKT_CALCULATOR,
  );
  const katalogConvos = all.filter(
    (c) => c.prompt_type === PROMPT_TYPE_KATALOG_CHAT,
  );

  return (
    <aside className="flex h-full w-64 flex-col border-r border-zinc-950/5 bg-zinc-50 dark:border-white/5 dark:bg-zinc-950">
      <div className="border-b border-zinc-950/5 p-3 dark:border-white/5">
        <Link
          to="/"
          className="block px-1 text-sm font-semibold text-zinc-900 transition hover:text-blue-600 dark:text-zinc-100 dark:hover:text-blue-400"
        >
          Roadbuilders Assistant
        </Link>
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
          <div className={SECTION_LABEL}>Katalog</div>
          <button
            type="button"
            onClick={() => void startKatalogChat()}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-zinc-700 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <BookOpenIcon className="h-4 w-4 shrink-0 text-zinc-400" />
            Neuer Katalog-Chat
          </button>
          {!isLoading && !isError && katalogConvos.length > 0 && (
            <ConversationList items={katalogConvos} emptyHint="" />
          )}
        </div>

        <div className="flex flex-col gap-1">
          <div className={SECTION_LABEL}>Project Conversations</div>
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
              items={projectConvos}
              emptyHint="No project conversations yet."
            />
          )}
        </div>
      </div>
    </aside>
  );
}
