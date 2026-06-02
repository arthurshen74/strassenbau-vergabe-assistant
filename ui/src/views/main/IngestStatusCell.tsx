// Renders one document's live ingest status as a badge (+ current phase while running).

import { Badge } from '../../components/ui/badge';
import { ingestPhaseLabel } from '../../lib/ingestPhaseLabel';
import type { DocIngestStatus } from '../../api/ingest';

export function IngestStatusCell({ status }: { status: DocIngestStatus | undefined }) {
  if (!status) {
    // No event yet on this connection (e.g. an older, already-finished document).
    return <span className="text-zinc-400">—</span>;
  }
  switch (status.status) {
    case 'queued':
      return <Badge color="zinc">Queued</Badge>;
    case 'running':
      return (
        <span className="inline-flex items-center gap-2">
          <Badge color="blue">Running</Badge>
          <span className="animate-pulse text-xs text-zinc-500 dark:text-zinc-400">
            {ingestPhaseLabel(status.phase)}…
          </span>
        </span>
      );
    case 'done':
      return <Badge color="green">Done</Badge>;
    case 'failed':
      return (
        <Badge color="red" title={status.message}>
          Failed
        </Badge>
      );
  }
}
