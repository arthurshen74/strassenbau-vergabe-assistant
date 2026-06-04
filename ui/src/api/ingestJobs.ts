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

export interface IngestJobFilters {
  status?: IngestJobStatus;
  project_uuid?: string;
  [key: string]: string | undefined;
}

function queryString(params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') sp.set(k, v);
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const ingestJobKeys = {
  all: ['ingest-jobs'] as const,
  list: (f: IngestJobFilters) => [...ingestJobKeys.all, f] as const,
};

export function useIngestJobs(filters: IngestJobFilters) {
  return useQuery({
    queryKey: ingestJobKeys.list(filters),
    queryFn: () =>
      api.get<IngestJobConsoleRead[]>(`/ingest-jobs${queryString(filters)}`),
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
