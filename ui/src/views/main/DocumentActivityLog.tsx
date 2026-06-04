// The document's ingestion activity (active table ∪ archive), oldest first, paged.

import { useState } from 'react';

import { useDocumentActivity } from '../../api/documents';
import { Button } from '../../components/ui/button';
import { Text } from '../../components/ui/text';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/ui/table';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { formatTimestamp } from '../../lib/format';

const PAGE_SIZE = 100;

export function DocumentActivityLog({
  projectUuid,
  documentUuid,
}: {
  projectUuid: string;
  documentUuid: string;
}) {
  const [offset, setOffset] = useState(0);
  const query = useDocumentActivity(projectUuid, documentUuid, offset, PAGE_SIZE);
  const rows = query.data ?? [];

  if (query.isPending) return <LoadingState label="Loading activity…" />;
  if (query.isError) {
    return <ErrorState message={(query.error as Error).message} onRetry={() => query.refetch()} />;
  }

  return (
    <div className="flex flex-col gap-3">
      {rows.length === 0 ? (
        <Text>No ingestion activity recorded.</Text>
      ) : (
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader>When</TableHeader>
              <TableHeader>Phase</TableHeader>
              <TableHeader>Message</TableHeader>
              <TableHeader>Worker</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="text-zinc-500">{formatTimestamp(r.ts)}</TableCell>
                <TableCell>{r.phase ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs">{r.message}</TableCell>
                <TableCell className="font-mono text-xs text-zinc-500">{r.worker_id}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <div className="flex items-center justify-end gap-2">
        <Button plain disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </Button>
        <Text className="text-xs">
          rows {rows.length === 0 ? 0 : offset + 1}–{offset + rows.length}
        </Text>
        <Button plain disabled={rows.length < PAGE_SIZE} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Next
        </Button>
      </div>
    </div>
  );
}
