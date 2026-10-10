// Query / mutation / stream hooks for the ingest console (Option D of crash recovery):
// list ingest and Projektinfo jobs with their lease + retry state and latest activity line,
// kept live by a server-side diffed SSE stream; requeue a stuck/failed job in place; and tail
// a job's granular activity over SSE.

import { useEffect, useState } from 'react';
import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { api } from './client';
import { projectKeys } from './projects';
import { openEventStream } from './sse';
import { log } from '../lib/logger';
import {
  parseActivityPayload,
  parseConsoleJobsPayload,
  parseProjectInfoActivityPayload,
} from '../lib/sse-events';
import type {
  ConsoleJobRead,
  ConsoleJobsSnapshot,
  IngestActivityLine,
  ProjectInfoActivityLine,
} from '../types/generated';

export type ConsoleJobStatus = ConsoleJobRead['status'];
export type ConsoleJobKind = ConsoleJobRead['kind'];
export type ActivityLine = IngestActivityLine | ProjectInfoActivityLine;

export const KIND_PROJECT_INFO: ConsoleJobKind = 'project_info';

export interface ConsoleJobFilters {
  statuses?: ConsoleJobStatus[];
  project_uuid?: string;
  // Open jobs plus jobs finished in the last few minutes (window is server-side).
  active?: boolean;
}

function buildQuery(filters: ConsoleJobFilters): string {
  const sp = new URLSearchParams();
  for (const status of filters.statuses ?? []) sp.append('status', status);
  if (filters.project_uuid) sp.set('project_uuid', filters.project_uuid);
  if (filters.active) sp.set('active', 'true');
  const s = sp.toString();
  return s ? `?${s}` : '';
}

// Keyed by the serialized filters so the list query and its stream share one cache entry.
export const ingestJobKeys = {
  all: ['ingest-jobs'] as const,
  list: (query: string) => [...ingestJobKeys.all, 'list', query] as const,
};

const RECONNECT_DELAY_MS = 1500;

// A Projektinfo job that just turned done has written the project header columns.
function invalidateFinishedProjectInfo(
  qc: QueryClient,
  prev: ConsoleJobRead[] | undefined,
  next: ConsoleJobRead[],
) {
  if (!prev) return;
  const prevStatus = new Map(prev.map((job) => [job.job_uuid, job.status]));
  for (const job of next) {
    if (job.kind !== KIND_PROJECT_INFO || job.status !== 'done') continue;
    const before = prevStatus.get(job.job_uuid);
    if (before === undefined || before === 'done') continue;
    qc.invalidateQueries({ queryKey: projectKeys.detail(job.project_uuid) });
    qc.invalidateQueries({ queryKey: projectKeys.list() });
  }
}

// The console list. The REST query fills the cache once; a long-lived SSE stream for the same
// filters then overwrites it with every snapshot the server emits on change. `live` is true
// while the stream is connected. Reconnects after a delay on error; aborts on unmount or when
// the filters change.
export function useConsoleJobs(filters: ConsoleJobFilters) {
  const qc = useQueryClient();
  const query = buildQuery(filters);
  const [live, setLive] = useState(false);

  const list = useQuery({
    queryKey: ingestJobKeys.list(query),
    queryFn: () => api.get<ConsoleJobRead[]>(`/ingest-jobs${query}`),
  });

  useEffect(() => {
    const controller = new AbortController();
    const key = ingestJobKeys.list(query);
    let stopped = false;

    async function run() {
      while (!stopped) {
        try {
          await openEventStream<ConsoleJobsSnapshot>({
            path: `/ingest-jobs/stream${query}`,
            parse: parseConsoleJobsPayload,
            signal: controller.signal,
            onEvent: (snapshot) => {
              setLive(true);
              invalidateFinishedProjectInfo(
                qc,
                qc.getQueryData<ConsoleJobRead[]>(key),
                snapshot.jobs,
              );
              qc.setQueryData(key, snapshot.jobs);
            },
          });
        } catch (err) {
          if (stopped || controller.signal.aborted) return;
          log.sse.error('console_stream_error', { err: String(err) });
        }
        setLive(false);
        if (stopped) return;
        await new Promise((resolve) => setTimeout(resolve, RECONNECT_DELAY_MS));
      }
    }

    void run();
    return () => {
      stopped = true;
      controller.abort();
      setLive(false);
    };
  }, [query, qc]);

  return { list, live };
}

export function useRequeueIngestJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobUuid: string) => api.post(`/ingest-jobs/${jobUuid}/requeue`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestJobKeys.all });
    },
  });
}

export function useRequeueProjectInfoJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobUuid: string) =>
      api.post(`/ingest-jobs/project-info/${jobUuid}/requeue`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestJobKeys.all });
    },
  });
}

// Tail a job's granular activity over SSE, folding lines into an ordered array. `kind` picks
// the ingest or Projektinfo stream. The server ends the stream when the job is terminal and
// drained (clean return -> no reconnect); transient errors reconnect after a delay, and ids are
// monotonic so re-received lines are de-duped. The stream is aborted on unmount or when the job
// changes. Mirrors useProjectIngestStatus' lifecycle.
export function useIngestJobActivity(
  kind: ConsoleJobKind | undefined,
  jobUuid: string | undefined,
): ActivityLine[] {
  const [lines, setLines] = useState<ActivityLine[]>([]);

  useEffect(() => {
    if (!kind || !jobUuid) return;
    const controller = new AbortController();
    let stopped = false;
    const onEvent = (event: ActivityLine) => {
      setLines((prev) => {
        const last = prev[prev.length - 1];
        if (last && event.id <= last.id) return prev; // re-received on reconnect
        return [...prev, event];
      });
    };

    async function open() {
      if (kind === KIND_PROJECT_INFO) {
        await openEventStream<ProjectInfoActivityLine>({
          path: `/ingest-jobs/project-info/${jobUuid}/activity/stream`,
          parse: parseProjectInfoActivityPayload,
          signal: controller.signal,
          onEvent,
        });
        return;
      }
      await openEventStream<IngestActivityLine>({
        path: `/ingest-jobs/${jobUuid}/activity/stream`,
        parse: parseActivityPayload,
        signal: controller.signal,
        onEvent,
      });
    }

    async function run() {
      while (!stopped) {
        try {
          await open();
          return; // clean end: job terminal and drained
        } catch (err) {
          if (stopped || controller.signal.aborted) return;
          log.sse.error('activity_stream_error', { err: String(err) });
        }
        if (stopped) return;
        await new Promise((resolve) => setTimeout(resolve, RECONNECT_DELAY_MS));
      }
    }

    void run();
    return () => {
      stopped = true;
      controller.abort();
      setLines([]);
    };
  }, [kind, jobUuid]);

  return lines;
}
