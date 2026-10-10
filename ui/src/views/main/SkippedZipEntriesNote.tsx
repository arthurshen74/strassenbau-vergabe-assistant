// Dismissible note listing the ZIP entries a ZIP-first project create did not ingest.

import { XMarkIcon } from '@heroicons/react/16/solid';

export function SkippedZipEntriesNote({
  skipped,
  onDismiss,
}: {
  skipped: string[];
  onDismiss: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
      <div className="flex min-w-0 flex-col gap-1">
        <span className="font-medium">
          {skipped.length} ZIP {skipped.length === 1 ? 'entry was' : 'entries were'} not ingested
          (only PDF, .x83 and .d83 are)
        </span>
        <ul className="max-h-32 overflow-y-auto font-mono text-xs">
          {skipped.map((path) => (
            <li key={path} className="truncate" title={path}>
              {path}
            </li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={onDismiss}
        className="shrink-0 rounded p-1 hover:bg-amber-100 dark:hover:bg-white/10"
      >
        <XMarkIcon className="h-4 w-4" />
      </button>
    </div>
  );
}
