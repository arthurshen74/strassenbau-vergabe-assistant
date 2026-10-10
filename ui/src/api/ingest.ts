// Live per-document ingest status for a project, over the SSE stream.
//
// Opens GET /projects/{id}/ingest/stream while the component is mounted and folds
// each IngestEvent into a map keyed by document_uuid. The stream is long-lived
// (it also catches files uploaded later), so it reconnects on transient errors and
// is aborted on unmount. When a document finishes ingesting, the project's documents and
// LV data have changed, so we invalidate those queries off the same stream.

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { openEventStream } from './sse';
import { projectKeys } from './projects';
import { log } from '../lib/logger';
import { parseIngestPayload } from '../lib/sse-events';
import type { IngestEvent, IngestJobRead } from '../types/generated';

export type IngestStatusValue = IngestJobRead['status'];

export interface DocIngestStatus {
  status: IngestStatusValue;
  phase?: string;
  message?: string;
}

const RECONNECT_DELAY_MS = 1500;

function toStatus(event: IngestEvent): DocIngestStatus {
  switch (event.event) {
    case 'ingest_queued':
      return { status: 'queued' };
    case 'ingest_started':
      return { status: 'running' };
    case 'ingest_progress':
      return { status: 'running', phase: event.phase, message: event.message };
    case 'ingest_completed':
      return { status: 'done' };
    case 'ingest_skipped':
      return { status: 'skipped' };
    case 'ingest_error':
      return { status: 'failed', phase: event.phase ?? undefined, message: event.message };
  }
}

export function useProjectIngestStatus(
  projectUuid: string | undefined,
): Record<string, DocIngestStatus> {
  const [statuses, setStatuses] = useState<Record<string, DocIngestStatus>>({});
  const qc = useQueryClient();

  useEffect(() => {
    if (!projectUuid) return;
    const uuid = projectUuid;
    const controller = new AbortController();
    let stopped = false;

    async function run() {
      while (!stopped) {
        try {
          await openEventStream<IngestEvent>({
            path: `/projects/${projectUuid}/ingest/stream`,
            parse: parseIngestPayload,
            signal: controller.signal,
            onEvent: (event) => {
              setStatuses((prev) => ({
                ...prev,
                [event.document_uuid]: toStatus(event),
              }));
              // Completed ingest means new LV items and texts. The lv-items prefix covers any
              // active search; the documents prefix covers the per-document LV queries.
              if (event.event === 'ingest_completed') {
                void qc.invalidateQueries({ queryKey: projectKeys.lvItems(uuid) });
                void qc.invalidateQueries({ queryKey: projectKeys.lvTexts(uuid) });
                void qc.invalidateQueries({ queryKey: projectKeys.documents(uuid) });
              }
            },
          });
        } catch (err) {
          if (stopped || controller.signal.aborted) return;
          log.sse.error('ingest_stream_error', { err: String(err) });
        }
        if (stopped) return;
        await new Promise((resolve) => setTimeout(resolve, RECONNECT_DELAY_MS));
      }
    }

    void run();
    return () => {
      stopped = true;
      controller.abort();
      setStatuses({});
    };
  }, [projectUuid, qc]);

  return statuses;
}
