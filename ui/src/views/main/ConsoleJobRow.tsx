// One ingest-console row: an ingest or Projektinfo job with its current step inline.

import { ArrowPathIcon, CommandLineIcon } from "@heroicons/react/16/solid";

import {
  KIND_PROJECT_INFO,
  type ConsoleJobStatus,
} from "../../api/ingestJobs";
import { Badge } from "../../components/ui/badge";
import { TableCell, TableRow } from "../../components/ui/table";
import type { ConsoleJobRead } from "../../types/generated";

const STATUS_COLOR: Record<
  ConsoleJobStatus,
  "zinc" | "blue" | "green" | "red"
> = {
  queued: "zinc",
  running: "blue",
  done: "green",
  failed: "red",
};

const ACTION =
  "inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium disabled:opacity-50";

// Seconds-resolution age so a running step visibly ticks.
function stepAge(iso: string, now: number): string {
  const sec = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  return `${Math.round(min / 60)}h ago`;
}

export function ConsoleJobRow({
  job,
  now,
  requeuePending,
  onActivity,
  onRequeue,
}: {
  job: ConsoleJobRead;
  now: number;
  requeuePending: boolean;
  onActivity: () => void;
  onRequeue: () => void;
}) {
  const step = [job.latest_phase && `[${job.latest_phase}]`, job.latest_message]
    .filter(Boolean)
    .join(" ");

  return (
    <TableRow>
      <TableCell>{job.project_name}</TableCell>
      <TableCell className="font-medium">
        {job.kind === KIND_PROJECT_INFO ? (
          <Badge color="indigo">Projektinfo</Badge>
        ) : (
          job.file_name
        )}
      </TableCell>
      <TableCell>
        <Badge color={STATUS_COLOR[job.status]}>{job.status}</Badge>
      </TableCell>
      <TableCell className="max-w-md">
        {job.latest_message ? (
          <div className="flex items-baseline gap-2 text-xs" title={step}>
            <span className="min-w-0 truncate">
              {job.latest_phase && (
                <span className="text-amber-600 dark:text-amber-400">
                  [{job.latest_phase}]{" "}
                </span>
              )}
              {job.latest_message}
            </span>
            {job.latest_ts && (
              <span className="shrink-0 text-zinc-400">
                {stepAge(job.latest_ts, now)}
              </span>
            )}
          </div>
        ) : (
          <span className="text-xs text-zinc-400">—</span>
        )}
      </TableCell>
      <TableCell>{job.attempts}</TableCell>
      <TableCell className="font-mono text-xs text-zinc-500">
        {job.locked_by ?? "—"}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onActivity}
            className={`${ACTION} text-sky-600 hover:bg-sky-50 dark:text-sky-400 dark:hover:bg-sky-500/10`}
          >
            <CommandLineIcon className="size-4" />
            Activity
          </button>
          <button
            type="button"
            disabled={requeuePending}
            onClick={onRequeue}
            className={`${ACTION} text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-500/10`}
          >
            <ArrowPathIcon className="size-4" />
            Requeue
          </button>
        </div>
      </TableCell>
    </TableRow>
  );
}
