// Live terminal for one ingest job: streams its granular activity as a scrolling log.

import { useLayoutEffect, useRef } from 'react';

import { useIngestJobActivity } from '../../api/ingestJobs';
import { Dialog, DialogBody, DialogTitle } from '../../components/ui/dialog';
import { formatTimestamp } from '../../lib/format';

export function IngestActivityTerminal({
  jobUuid,
  onClose,
}: {
  jobUuid: string | null;
  onClose: () => void;
}) {
  const lines = useIngestJobActivity(jobUuid ?? undefined);
  const endRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [lines.length]);

  return (
    <Dialog open={jobUuid !== null} onClose={onClose} size="3xl">
      <DialogTitle>Ingestion activity</DialogTitle>
      <DialogBody>
        <div className="max-h-[60vh] overflow-y-auto rounded bg-zinc-950 p-3 font-mono text-xs text-zinc-100">
          {lines.length === 0 ? (
            <div className="text-zinc-500">Waiting for activity…</div>
          ) : (
            lines.map((line) => (
              <div key={line.id} className="whitespace-pre-wrap">
                <span className="text-zinc-500">{formatTimestamp(line.ts)} </span>
                {line.phase && <span className="text-amber-400">[{line.phase}] </span>}
                <span>{line.message}</span>
                <span className="text-zinc-600"> · {line.worker_id}</span>
              </div>
            ))
          )}
          <div ref={endRef} />
        </div>
      </DialogBody>
    </Dialog>
  );
}
