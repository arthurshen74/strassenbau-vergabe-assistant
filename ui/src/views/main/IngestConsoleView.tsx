// Ingest console (Option D): list ingest jobs with their lease/retry state, requeue a stuck or
// failed job in place, and watch a job's live activity terminal.

import { useState } from 'react';
import { ArrowPathIcon } from '@heroicons/react/16/solid';

import {
  useIngestJobs,
  useRequeueIngestJob,
  type IngestJobStatus,
} from '../../api/ingestJobs';
import { Heading } from '../../components/ui/heading';
import { Text } from '../../components/ui/text';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
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
import { IngestActivityTerminal } from './IngestActivityTerminal';

const STATUSES: IngestJobStatus[] = ['queued', 'running', 'done', 'failed'];

const STATUS_COLOR: Record<IngestJobStatus, 'zinc' | 'blue' | 'green' | 'red'> = {
  queued: 'zinc',
  running: 'blue',
  done: 'green',
  failed: 'red',
};

export function IngestConsoleView() {
  const [status, setStatus] = useState<IngestJobStatus | ''>('');
  const [activityJob, setActivityJob] = useState<string | null>(null);

  const query = useIngestJobs({ status: status || undefined });
  const requeue = useRequeueIngestJob();
  const rows = query.data ?? [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <Heading level={4}>Ingest Console</Heading>
        <Button
          plain
          disabled={query.isFetching}
          onClick={() => query.refetch()}
          aria-label="Refresh jobs"
        >
          <ArrowPathIcon className={query.isFetching ? 'animate-spin' : undefined} />
          Refresh
        </Button>
      </div>

      <label className="flex w-56 flex-col gap-1 text-xs text-zinc-500">
        Status
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value as IngestJobStatus | '')}
        >
          <option value="">All</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </label>

      {query.isPending ? (
        <LoadingState label="Loading jobs…" />
      ) : query.isError ? (
        <ErrorState
          message={(query.error as Error).message}
          onRetry={() => query.refetch()}
        />
      ) : rows.length === 0 ? (
        <Text>No ingest jobs.</Text>
      ) : (
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader>Status</TableHeader>
              <TableHeader>Attempts</TableHeader>
              <TableHeader>Worker</TableHeader>
              <TableHeader>Updated</TableHeader>
              <TableHeader>Actions</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((job) => (
              <TableRow key={job.job_uuid}>
                <TableCell>
                  <Badge color={STATUS_COLOR[job.status]}>{job.status}</Badge>
                </TableCell>
                <TableCell>{job.attempts}</TableCell>
                <TableCell className="font-mono text-xs text-zinc-500">
                  {job.locked_by ?? '—'}
                </TableCell>
                <TableCell className="text-zinc-500">
                  {formatTimestamp(job.updated_at)}
                </TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button plain onClick={() => setActivityJob(job.job_uuid)}>
                      Activity
                    </Button>
                    <Button
                      plain
                      disabled={requeue.isPending}
                      onClick={() => requeue.mutate(job.job_uuid)}
                    >
                      Requeue
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <IngestActivityTerminal jobUuid={activityJob} onClose={() => setActivityJob(null)} />
    </div>
  );
}
