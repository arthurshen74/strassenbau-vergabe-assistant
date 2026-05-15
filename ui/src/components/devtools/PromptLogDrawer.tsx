// Right-side drawer that lists recent prompt execution log entries.
// Clicking a row opens PromptLogDetailModal for the full detail.

import { useState } from 'react';
import * as Headless from '@headlessui/react';
import {
  ArrowPathIcon,
  ClipboardDocumentListIcon,
  XMarkIcon,
} from '@heroicons/react/20/solid';
import { usePromptExecutionLogs } from '../../api/prompt_execution_logs';
import type { PromptExecutionLogSummaryDTO } from '../../types/generated';
import { PromptLogDetailModal } from './PromptLogDetailModal';

// ---------------------------------------------------------------------------
// Compact badge for the prompt type.
// ---------------------------------------------------------------------------
const TYPE_COLORS: Record<string, string> = {
  dispatcher:
    'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  interviewer:
    'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  evaluator:
    'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  judge:
    'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  utility:
    'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300',
};

function TypeBadge({ type }: { type: string }) {
  const cls =
    TYPE_COLORS[type] ??
    'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300';
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {type}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Single list row.
// ---------------------------------------------------------------------------
function LogRow({
  entry,
  onClick,
}: {
  entry: PromptExecutionLogSummaryDTO;
  onClick: () => void;
}) {
  const sentAt = new Date(entry.sent_at);
  const tokenStr =
    entry.tokens_in !== null && entry.tokens_out !== null
      ? `${entry.tokens_in} / ${entry.tokens_out} tok`
      : '— tok';

  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full flex-col gap-1 border-b border-zinc-100 px-4 py-3 text-left transition hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
    >
      <div className="flex items-center gap-2">
        <TypeBadge type={entry.prompt_type} />
        <span className="flex-1 truncate text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {entry.prompt_name}
        </span>
        <span className="shrink-0 text-[10px] text-zinc-400">
          v{entry.prompt_version}
        </span>
      </div>
      <div className="flex items-center gap-3 text-[11px] text-zinc-500 dark:text-zinc-400">
        <span>{sentAt.toLocaleDateString()} {sentAt.toLocaleTimeString()}</span>
        <span className="ml-auto">{entry.duration_ms.toLocaleString()} ms</span>
        <span>{tokenStr}</span>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Public component — the drawer itself.
// ---------------------------------------------------------------------------
export function PromptLogDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { data, isLoading, isError, refetch, isFetching } =
    usePromptExecutionLogs();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <>
      <Headless.Dialog open={open} onClose={onClose} className="relative z-40">
        {/* Backdrop — semi-transparent but lighter than the detail modal */}
        <Headless.DialogBackdrop className="fixed inset-0 bg-zinc-950/20 transition duration-200 data-closed:opacity-0" />

        {/* Slide-in panel from the right */}
        <div className="fixed inset-0 flex justify-end">
          <Headless.DialogPanel className="flex h-full w-[420px] flex-col bg-white shadow-2xl ring-1 ring-zinc-950/5 transition duration-200 data-closed:translate-x-full dark:bg-zinc-900 dark:ring-white/10">
            {/* Header */}
            <div className="flex shrink-0 items-center gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-700">
              <ClipboardDocumentListIcon className="h-5 w-5 text-zinc-400" />
              <Headless.DialogTitle className="flex-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                Prompt Execution Log
              </Headless.DialogTitle>
              <button
                type="button"
                onClick={() => refetch()}
                disabled={isFetching}
                title="Refresh"
                className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 disabled:opacity-40 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                <ArrowPathIcon
                  className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`}
                />
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            {/* Entry count sub-header */}
            {data && (
              <div className="shrink-0 border-b border-zinc-100 px-4 py-2 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                {data.length} {data.length === 1 ? 'entry' : 'entries'} · newest
                first
              </div>
            )}

            {/* Log list */}
            <div className="flex-1 overflow-y-auto">
              {isLoading && (
                <p className="px-4 py-6 text-sm text-zinc-500">Loading…</p>
              )}
              {isError && (
                <p className="px-4 py-6 text-sm text-red-600 dark:text-red-400">
                  Failed to load logs.
                </p>
              )}
              {data && data.length === 0 && (
                <div className="flex flex-col items-center gap-2 py-16 text-center">
                  <ClipboardDocumentListIcon className="h-8 w-8 text-zinc-300 dark:text-zinc-600" />
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    No prompt executions yet.
                  </p>
                  <p className="text-xs text-zinc-400 dark:text-zinc-500">
                    Entries appear here after the first LLM call.
                  </p>
                </div>
              )}
              {data &&
                data.map((entry) => (
                  <LogRow
                    key={entry.id}
                    entry={entry}
                    onClick={() => setSelectedId(entry.id)}
                  />
                ))}
            </div>
          </Headless.DialogPanel>
        </div>
      </Headless.Dialog>

      {/* Detail modal — opened over the drawer */}
      <PromptLogDetailModal
        logId={selectedId}
        open={selectedId !== null}
        onClose={() => setSelectedId(null)}
      />
    </>
  );
}
