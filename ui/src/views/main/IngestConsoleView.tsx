// Ingest console (Option D): ingest and Projektinfo jobs with their lease/retry state and
// current step, kept live by the server's list stream; requeue a stuck or failed job in place,
// and watch a job's live activity terminal. Opened after an upload with
// `data: IngestConsoleData`, it starts filtered to that project.

import { useEffect, useState } from "react";
import { XMarkIcon } from "@heroicons/react/16/solid";

import {
  KIND_PROJECT_INFO,
  useConsoleJobs,
  useRequeueIngestJob,
  useRequeueProjectInfoJob,
  type ConsoleJobKind,
  type ConsoleJobStatus,
} from "../../api/ingestJobs";
import { useProject } from "../../api/projects";
import { Heading } from "../../components/ui/heading";
import { Text } from "../../components/ui/text";
import { Select } from "../../components/ui/select";
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { LoadingState } from "../../components/feedback/LoadingState";
import { ErrorState } from "../../components/feedback/ErrorState";
import { ConsoleJobRow } from "./ConsoleJobRow";
import { IngestActivityTerminal } from "./IngestActivityTerminal";
import { SkippedZipEntriesNote } from "./SkippedZipEntriesNote";

export interface IngestConsoleData {
  projectUuid: string;
  // ZIP entries a ZIP-first project create did not ingest.
  skipped?: string[];
}

type StatusFilter = "active" | "all" | ConsoleJobStatus;

const FILTER_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "all", label: "All" },
  { value: "queued", label: "queued" },
  { value: "running", label: "running" },
  { value: "done", label: "done" },
  { value: "failed", label: "failed" },
  { value: "skipped", label: "skipped" },
];

const CLOCK_TICK_MS = 1000;

function narrow(data: unknown): IngestConsoleData | null {
  if (typeof data !== "object" || data === null || !("projectUuid" in data)) {
    return null;
  }
  const { projectUuid, skipped } = data as Record<string, unknown>;
  if (typeof projectUuid !== "string") return null;
  return {
    projectUuid,
    skipped: Array.isArray(skipped)
      ? skipped.filter((s): s is string => typeof s === "string")
      : undefined,
  };
}

// Re-renders once a second so the "Current step" ages tick between snapshots.
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), CLOCK_TICK_MS);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function IngestConsoleView({ data }: { data?: unknown }) {
  const opened = narrow(data);
  const [seenData, setSeenData] = useState(data);
  const [filter, setFilter] = useState<StatusFilter>("active");
  const [projectUuid, setProjectUuid] = useState(opened?.projectUuid ?? null);
  const [skipped, setSkipped] = useState(opened?.skipped ?? []);
  const [activityJob, setActivityJob] = useState<{
    kind: ConsoleJobKind;
    jobUuid: string;
  } | null>(null);
  // Re-opened with new data while mounted: adopt its project filter and skipped note.
  if (data !== seenData) {
    setSeenData(data);
    setProjectUuid(opened?.projectUuid ?? null);
    setSkipped(opened?.skipped ?? []);
  }

  const now = useNow();
  const { list, live } = useConsoleJobs({
    active: filter === "active",
    statuses: filter === "active" || filter === "all" ? undefined : [filter],
    project_uuid: projectUuid ?? undefined,
  });
  const project = useProject(projectUuid ?? undefined);
  const requeueIngest = useRequeueIngestJob();
  const requeueProjectInfo = useRequeueProjectInfoJob();
  const rows = list.data ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex shrink-0 flex-col gap-3">
        <div className="flex items-center gap-2">
          <Heading level={4}>Ingest Console</Heading>
          <span
            className={`size-2 rounded-full ${live ? "bg-green-500" : "bg-zinc-400"}`}
            title={live ? "Live" : "Reconnecting…"}
            aria-label={live ? "Live" : "Reconnecting"}
          />
        </div>

        <div className="flex items-end gap-3">
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
          {projectUuid && (
            <span className="mb-1 inline-flex items-center gap-1 rounded-full bg-zinc-100 py-1 pr-1 pl-3 text-xs text-zinc-700 dark:bg-white/10 dark:text-zinc-200">
              Project: {project.data?.project_name ?? "…"}
              <button
                type="button"
                aria-label="Show all projects"
                onClick={() => setProjectUuid(null)}
                className="rounded-full p-0.5 hover:bg-zinc-200 dark:hover:bg-white/10"
              >
                <XMarkIcon className="size-3.5" />
              </button>
            </span>
          )}
        </div>

        {skipped.length > 0 && (
          <SkippedZipEntriesNote
            skipped={skipped}
            onDismiss={() => setSkipped([])}
          />
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {list.isPending ? (
          <LoadingState label="Loading jobs…" />
        ) : list.isError ? (
          <ErrorState
            message={(list.error as Error).message}
            onRetry={() => list.refetch()}
          />
        ) : rows.length === 0 ? (
          <Text>No jobs.</Text>
        ) : (
          <Table dense>
            <TableHead>
              <TableRow>
                <TableHeader>Project</TableHeader>
                <TableHeader>File</TableHeader>
                <TableHeader>Status</TableHeader>
                <TableHeader>Current step</TableHeader>
                <TableHeader>Attempts</TableHeader>
                <TableHeader>Worker</TableHeader>
                <TableHeader>Actions</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((job) => {
                const requeue =
                  job.kind === KIND_PROJECT_INFO
                    ? requeueProjectInfo
                    : requeueIngest;
                return (
                  <ConsoleJobRow
                    key={job.job_uuid}
                    job={job}
                    now={now}
                    requeuePending={requeue.isPending}
                    onActivity={() =>
                      setActivityJob({ kind: job.kind, jobUuid: job.job_uuid })
                    }
                    onRequeue={() => requeue.mutate(job.job_uuid)}
                  />
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>

      <IngestActivityTerminal
        kind={activityJob?.kind ?? null}
        jobUuid={activityJob?.jobUuid ?? null}
        onClose={() => setActivityJob(null)}
      />
    </div>
  );
}
