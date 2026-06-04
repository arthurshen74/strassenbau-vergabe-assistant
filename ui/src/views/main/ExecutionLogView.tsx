// Prompt execution log: filterable, paged table + a detail modal per row.

import { useState } from 'react';
import { ArrowPathIcon } from '@heroicons/react/16/solid';
import {
  usePromptExecutionLog,
  usePromptExecutionLogs,
  type ExecutionLogFilters,
} from '../../api/logs';
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
import { Dialog, DialogBody, DialogTitle } from '../../components/ui/dialog';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { formatTimestamp } from '../../lib/format';

const PROMPT_TYPES = [
  'dispatcher',
  'project_chat',
  'classify_project_chat_user_message',
  'aggregate_lv_membership',
  'multi_question_generator',
  'lv_extraction',
  'conversation_name',
];
const PAGE_SIZE = 100;

// The backend filters `created_at < end`; advance the picked end date by a day so
// the whole selected day is included.
function nextDay(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

export function ExecutionLogView() {
  const [promptType, setPromptType] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  const filters: ExecutionLogFilters = {
    prompt_type: promptType || undefined,
    start: start || undefined,
    end: end ? nextDay(end) : undefined,
    limit: PAGE_SIZE,
    offset,
  };
  const query = usePromptExecutionLogs(filters);
  const rows = query.data ?? [];

  const onFilter = (set: (v: string) => void) => (e: { target: { value: string } }) => {
    set(e.target.value);
    setOffset(0);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <Heading level={4}>Prompt Execution Log</Heading>
        <Button
          plain
          disabled={query.isFetching}
          onClick={() => query.refetch()}
          aria-label="Refresh logs"
        >
          <ArrowPathIcon className={query.isFetching ? 'animate-spin' : undefined} />
          Refresh
        </Button>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-zinc-500">
          Prompt type
          <Select value={promptType} onChange={onFilter(setPromptType)} className="w-56">
            <option value="">All</option>
            {PROMPT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
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
        <LoadingState label="Loading logs…" />
      ) : query.isError ? (
        <ErrorState message={(query.error as Error).message} onRetry={() => query.refetch()} />
      ) : rows.length === 0 ? (
        <Text>No log entries.</Text>
      ) : (
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader>Type</TableHeader>
              <TableHeader>Ver</TableHeader>
              <TableHeader>Model</TableHeader>
              <TableHeader>Tokens (in/out)</TableHeader>
              <TableHeader>Latency</TableHeader>
              <TableHeader>OK</TableHeader>
              <TableHeader>When</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.log_uuid} className="cursor-pointer" onClick={() => setSelected(r.log_uuid)}>
                <TableCell>{r.prompt_type ?? '—'}</TableCell>
                <TableCell>{r.prompt_version ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs">{r.model}</TableCell>
                <TableCell>
                  {r.tokens_in ?? '—'} / {r.tokens_out ?? '—'}
                </TableCell>
                <TableCell>{r.latency_ms != null ? `${r.latency_ms} ms` : '—'}</TableCell>
                <TableCell>
                  <Badge color={r.success ? 'green' : 'red'}>{r.success ? 'ok' : 'fail'}</Badge>
                </TableCell>
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

      <ExecutionLogDetail logUuid={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function ExecutionLogDetail({ logUuid, onClose }: { logUuid: string | null; onClose: () => void }) {
  const query = usePromptExecutionLog(logUuid ?? undefined);
  const d = query.data;
  return (
    <Dialog open={logUuid !== null} onClose={onClose} size="3xl">
      <DialogTitle>Execution detail</DialogTitle>
      <DialogBody className="flex flex-col gap-3 text-sm">
        {query.isPending && <LoadingState label="Loading…" />}
        {d && (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Detail label="Model" value={d.model} />
              <Detail label="Type" value={`${d.prompt_type ?? '—'} v${d.prompt_version ?? '—'}`} />
              <Detail label="Finish" value={d.finish_reason ?? '—'} />
              <Detail label="Tokens" value={`${d.tokens_in ?? '—'} / ${d.tokens_out ?? '—'}`} />
              <Detail label="Latency" value={d.latency_ms != null ? `${d.latency_ms} ms` : '—'} />
              <Detail label="Success" value={String(d.success)} />
            </div>
            {d.error_message && <div className="text-red-600">{d.error_message}</div>}
            <JsonBlock label="System prompt" value={d.system_prompt} />
            <JsonBlock label="Messages" value={JSON.stringify(d.messages, null, 2)} />
            {d.response_text && <JsonBlock label="Response text" value={d.response_text} />}
            {d.response_tool_calls && (
              <JsonBlock label="Tool calls" value={JSON.stringify(d.response_tool_calls, null, 2)} />
            )}
            {d.response_structured && (
              <JsonBlock label="Structured output" value={JSON.stringify(d.response_structured, null, 2)} />
            )}
          </>
        )}
      </DialogBody>
    </Dialog>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="text-zinc-900 dark:text-zinc-100">{value}</span>
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <details>
      <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-200">
        {label}
      </summary>
      <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-2 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
        {value}
      </pre>
    </details>
  );
}
