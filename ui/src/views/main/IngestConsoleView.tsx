// Ingest console (Option D): list ingest jobs with their lease/retry state, requeue a stuck or
// failed job in place, and watch a job's live activity terminal.

import { useState } from "react";
import { ArrowPathIcon, CommandLineIcon } from "@heroicons/react/16/solid";

import {
  ACTIVE_STATUSES,
  useIngestJobs,
  useRequeueIngestJob,
  type IngestJobStatus,
} from "../../api/ingestJobs";
import { Heading } from "../../components/ui/heading";
import { Text } from "../../components/ui/text";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Select } from "../../components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { LoadingState } from "../../components/feedback/LoadingState";
import { ErrorState } from "../../components/feedback/ErrorState";
import { formatTimestamp } from "../../lib/format";
import { IngestActivityTerminal } from "./IngestActivityTerminal";

type StatusFilter = "" | "active" | IngestJobStatus;

const FILTER_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "", label: "All" },
  { value: "active", label: "Active / Queued" },
  { value: "queued", label: "queued" },
  { value: "running", label: "running" },
  { value: "done", label: "done" },
  { value: "failed", label: "failed" },
];

function filterStatuses(filter: StatusFilter): IngestJobStatus[] | undefined {
  if (filter === "") return undefined;
  if (filter === "active") return ACTIVE_STATUSES;
  return [filter];
}

const STATUS_COLOR: Record<IngestJobStatus, "zinc" | "blue" | "green" | "red"> =
  {
    queued: "zinc",
    running: "blue",
    done: "green",
    failed: "red",
  };

const ACTION =
  "inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium disabled:opacity-50";

export function IngestConsoleView() {
  const [filter, setFilter] = useState<StatusFilter>("");
  const [activityJob, setActivityJob] = useState<string | null>(null);
  const [manualRefreshing, setManualRefreshing] = useState(false);

  const query = useIngestJobs({ statuses: filterStatuses(filter) });
  const requeue = useRequeueIngestJob();
  const rows = query.data ?? [];

  // The list polls in the background; reflect only manual refetches on the button so it doesn't
  // spin on every poll tick.
  const onRefresh = async () => {
    setManualRefreshing(true);
    try {
      await query.refetch();
    } finally {
      setManualRefreshing(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex shrink-0 flex-col gap-3">
        <div className="flex items-center justify-between">
          <Heading level={4}>Ingest Console</Heading>
          <Button
            plain
            disabled={manualRefreshing}
            onClick={onRefresh}
            aria-label="Refresh jobs"
          >
            <ArrowPathIcon
              className={manualRefreshing ? "animate-spin" : undefined}
            />
            Refresh
          </Button>
        </div>

        <label className="flex w-56 flex-col gap-1 text-xs text-zinc-500">
          Status
          <Select
            value={filter}
            onChange={(e) => setFilter(e.target.value as StatusFilter)}
          >
            {FILTER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {query.isPending ? (
          <LoadingState label="Loading jobs…" />
        ) : query.isError ? (
          <ErrorState
            message={(query.error as Error).message}
            onRetry={() => query.refetch()}
          />
        ) : rows.length === 0 ? (
          <Text>No ingest jobs.</Text>
        ) : (
          <Table dense>
            <TableHead>
              <TableRow>
                <TableHeader>ID</TableHeader>
                <TableHeader>Project</TableHeader>
                <TableHeader>File</TableHeader>
                <TableHeader>Status</TableHeader>
                <TableHeader>Attempts</TableHeader>
                <TableHeader>Worker</TableHeader>
                <TableHeader>Updated</TableHeader>
                <TableHeader>Actions</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((job) => (
                <TableRow key={job.job_uuid}>
                  <TableCell
                    className="font-mono text-xs text-zinc-500"
                    title={job.job_uuid}
                  >
                    {job.job_uuid.slice(0, 8)}
                  </TableCell>
                  <TableCell>{job.project_name}</TableCell>
                  <TableCell className="font-medium">{job.file_name}</TableCell>
                  <TableCell>
                    <Badge color={STATUS_COLOR[job.status]}>{job.status}</Badge>
                  </TableCell>
                  <TableCell>{job.attempts}</TableCell>
                  <TableCell className="font-mono text-xs text-zinc-500">
                    {job.locked_by ?? "—"}
                  </TableCell>
                  <TableCell className="text-zinc-500">
                    {formatTimestamp(job.updated_at)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setActivityJob(job.job_uuid)}
                        className={`${ACTION} text-sky-600 hover:bg-sky-50 dark:text-sky-400 dark:hover:bg-sky-500/10`}
                      >
                        <CommandLineIcon className="size-4" />
                        Activity
                      </button>
                      <button
                        type="button"
                        disabled={requeue.isPending}
                        onClick={() => requeue.mutate(job.job_uuid)}
                        className={`${ACTION} text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-500/10`}
                      >
                        <ArrowPathIcon className="size-4" />
                        Requeue
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <IngestActivityTerminal
        jobUuid={activityJob}
        onClose={() => setActivityJob(null)}
      />
    </div>
  );
}
