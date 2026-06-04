// The document's ingestion activity (active ∪ archive), oldest first, with numbered paging.

import { useState } from 'react';

import { useDocumentActivity } from '../../api/documents';
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
import { PageNav } from './PageNav';

const PAGE_SIZE = 50;

export function DocumentActivityLog({
  projectUuid,
  documentUuid,
}: {
  projectUuid: string;
  documentUuid: string;
}) {
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;
  const query = useDocumentActivity(projectUuid, documentUuid, offset, PAGE_SIZE);
  const rows = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

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
      <PageNav page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  );
}
