// OpenRouter usage log: filterable, paged table.

import { useState } from 'react';
import { useUsageLogs, type UsageFilters } from '../../api/logs';
import { Heading } from '../../components/ui/heading';
import { Text } from '../../components/ui/text';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Select } from '../../components/ui/select';
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

const OPERATIONS = ['CHAT', 'EMBEDDING', 'RERANK'];
const PAGE_SIZE = 100;

// Backend filters `created_at < end`; advance the picked end date by a day.
function nextDay(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function formatCost(cost: number | string | null | undefined): string {
  if (cost == null) return '—';
  return `$${Number(cost).toFixed(5)}`;
}

export function UsageLogView() {
  const [operation, setOperation] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [offset, setOffset] = useState(0);

  const filters: UsageFilters = {
    operation: operation || undefined,
    start: start || undefined,
    end: end ? nextDay(end) : undefined,
    limit: PAGE_SIZE,
    offset,
  };
  const query = useUsageLogs(filters);
  const rows = query.data ?? [];

  const onFilter = (set: (v: string) => void) => (e: { target: { value: string } }) => {
    set(e.target.value);
    setOffset(0);
  };

  return (
    <div className="flex flex-col gap-3">
      <Heading level={4}>Prompt Usage Log</Heading>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-zinc-500">
          Type
          <Select value={operation} onChange={onFilter(setOperation)} className="w-44">
            <option value="">All</option>
            {OPERATIONS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-zinc-500">
          From
          <Input type="date" value={start} onChange={onFilter(setStart)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-zinc-500">
          To
          <Input type="date" value={end} onChange={onFilter(setEnd)} />
        </label>
      </div>

      {query.isPending ? (
        <LoadingState label="Loading usage…" />
      ) : query.isError ? (
        <ErrorState message={(query.error as Error).message} onRetry={() => query.refetch()} />
      ) : rows.length === 0 ? (
        <Text>No usage entries.</Text>
      ) : (
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader>Operation</TableHeader>
              <TableHeader>Model</TableHeader>
              <TableHeader>Prompt</TableHeader>
              <TableHeader>Completion</TableHeader>
              <TableHeader>Total</TableHeader>
              <TableHeader>Cost</TableHeader>
              <TableHeader>When</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.usage_uuid}>
                <TableCell>
                  <Badge color="blue">{r.operation}</Badge>
                </TableCell>
                <TableCell className="font-mono text-xs">{r.model}</TableCell>
                <TableCell>{r.prompt_tokens ?? '—'}</TableCell>
                <TableCell>{r.completion_tokens ?? '—'}</TableCell>
                <TableCell>{r.total_tokens ?? '—'}</TableCell>
                <TableCell>{formatCost(r.cost)}</TableCell>
                <TableCell className="text-zinc-500">{formatTimestamp(r.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <div className="flex items-center justify-end gap-2">
        <Button plain disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </Button>
        <Text className="text-xs">rows {offset + 1}–{offset + rows.length}</Text>
        <Button plain disabled={rows.length < PAGE_SIZE} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Next
        </Button>
      </div>
    </div>
  );
}
