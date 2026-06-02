// Per-document (re-)ingest button. Queues a job; disabled while the document is already
// queued/running (from the live status stream) or while the request is in flight.

import { ArrowPathIcon } from '@heroicons/react/16/solid';
import { useIngestDocument } from '../../api/projects';
import { Button } from '../../components/ui/button';

export function IngestButton({
  projectUuid,
  documentUuid,
  active,
}: {
  projectUuid: string;
  documentUuid: string;
  active: boolean;
}) {
  const ingest = useIngestDocument(projectUuid);
  const disabled = active || ingest.isPending;
  return (
    <Button
      plain
      disabled={disabled}
      onClick={() => ingest.mutate(documentUuid)}
      aria-label="Ingest document"
    >
      <ArrowPathIcon className={ingest.isPending ? 'animate-spin' : undefined} />
      Ingest
    </Button>
  );
}
