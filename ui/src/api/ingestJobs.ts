// Query / mutation / stream hooks for the ingest console (Option D of crash recovery):
// list jobs with their lease + retry state, requeue a stuck/failed job in place, and tail a
// job's granular activity over SSE.

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import { openEventStream } from './sse';
import { log } from '../lib/logger';
import { parseActivityPayload } from '../lib/sse-events';
import type { IngestActivityLine, IngestJobConsoleRead } from '../types/generated';

export type IngestJobStatus = IngestJobConsoleRead['status'];

// Jobs not yet in a terminal state. Single source of truth for the "Active" filter and for the
// poll cadence below.
export const ACTIVE_STATUSES: IngestJobStatus[] = ['queued', 'running'];

// Poll fast while jobs are in flight; idle slowly otherwise so newly queued jobs still surface.
const ACTIVE_POLL_MS = 2500;
const IDLE_POLL_MS = 8000;

export interface IngestJobFilters {
  statuses?: IngestJobStatus[];
  project_uuid?: string;
}

function buildQuery(filters: IngestJobFilters): string {
  const sp = new URLSearchParams();
  for (const status of filters.statuses ?? []) sp.append('status', status);
  if (filters.project_uuid) sp.set('project_uuid', filters.project_uuid);
  const s = sp.toString();
  return s ? `?${s}` : '';
}

function hasActiveJobs(jobs: IngestJobConsoleRead[] | undefined): boolean {
  return jobs?.some((job) => ACTIVE_STATUSES.includes(job.status)) ?? false;
}

export const ingestJobKeys = {
  all: ['ingest-jobs'] as const,
  list: (f: IngestJobFilters) => [...ingestJobKeys.all, f] as const,
};

export function useIngestJobs(filters: IngestJobFilters) {
  return useQuery({
    queryKey: ingestJobKeys.list(filters),
    queryFn: () =>
      api.get<IngestJobConsoleRead[]>(`/ingest-jobs${buildQuery(filters)}`),
    refetchInterval: (query) =>
      hasActiveJobs(query.state.data) ? ACTIVE_POLL_MS : IDLE_POLL_MS,
    refetchIntervalInBackground: false,
  });
}

export function useRequeueIngestJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobUuid: string) =>
      api.post<IngestJobConsoleRead>(`/ingest-jobs/${jobUuid}/requeue`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestJobKeys.all });
    },
  });
}

const RECONNECT_DELAY_MS = 1500;

// Tail a job's granular activity over SSE, folding lines into an ordered array. The server ends
// the stream when the job is terminal and drained (clean return -> no reconnect); transient errors
// reconnect after a delay, and ids are monotonic so re-received lines are de-duped. The stream is
// aborted on unmount or when jobUuid changes. Mirrors useProjectIngestStatus' lifecycle.
export function useIngestJobActivity(
  jobUuid: string | undefined,
): IngestActivityLine[] {
  const [lines, setLines] = useState<IngestActivityLine[]>([]);

  useEffect(() => {
    if (!jobUuid) return;
    const controller = new AbortController();
    let stopped = false;

    async function run() {
      while (!stopped) {
        try {
          await openEventStream<IngestActivityLine>({
            path: `/ingest-jobs/${jobUuid}/activity/stream`,
            parse: parseActivityPayload,
            signal: controller.signal,
            onEvent: (event) => {
              setLines((prev) => {
                const last = prev[prev.length - 1];
                if (last && event.id <= last.id) return prev; // re-received on reconnect
                return [...prev, event];
              });
            },
          });
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
  }, [jobUuid]);

  return lines;
}
