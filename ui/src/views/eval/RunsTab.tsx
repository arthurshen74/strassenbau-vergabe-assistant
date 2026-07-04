// The Läufe tab: start an eval run (queued for the worker's eval loop) and watch
// it execute — status polls while active, an expanded run streams its progress
// events, and a finished run shows its metrics keyed to the prompt versions used.

import { Fragment, useState } from 'react';
import { ChevronRightIcon, PlayIcon } from '@heroicons/react/16/solid';
import clsx from 'clsx';
import {
  isActiveRun,
  useEnqueueEvalRun,
  useEvalRunEvents,
  useEvalRuns,
} from '../../api/evalRuns';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../components/ui/dialog';
import { Field, Label } from '../../components/ui/fieldset';
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
import { Text } from '../../components/ui/text';
import { LoadingState } from '../../components/feedback/LoadingState';
import { formatRelativeTime, formatTimestamp } from '../../lib/format';
import type { EvalRun, EvalRunCreate } from '../../types/generated';

const KIND_LABEL: Record<EvalRun['kind'], string> = {
  calculator_gold: 'Kalkulation-Gold',
  chat_values: 'Chat-Werte (Fixtures)',
  rag_retrieval: 'RAG-Retrieval',
  rag_answers: 'RAG-Antworten',
};

// Kinds the worker executes today (the backend rejects the rest at enqueue).
const STARTABLE_KINDS: EvalRun['kind'][] = ['calculator_gold', 'chat_values'];

const STATUS_BADGE: Record<EvalRun['status'], 'zinc' | 'blue' | 'lime' | 'red'> = {
  queued: 'zinc',
  running: 'blue',
  done: 'lime',
  failed: 'red',
};

function metricChips(run: EvalRun): [string, string][] {
  const metrics = (run.summary?.metrics ?? {}) as Record<string, unknown>;
  return Object.entries(metrics)
    .filter((e): e is [string, number] => typeof e[1] === 'number')
    .map(([k, v]) => [k, Number.isInteger(v) ? String(v) : v.toFixed(2)]);
}

function RunDetails({ run }: { run: EvalRun }) {
  const events = useEvalRunEvents(run.eval_run_uuid, isActiveRun(run));
  return (
    <div className="flex flex-col gap-3 py-2">
      {run.error && (
        <Text className="text-xs text-red-600 dark:text-red-400">{run.error}</Text>
      )}
      {run.prompt_versions && (
        <div className="text-xs text-zinc-500">
          Prompt-Versionen:{' '}
          <span className="font-mono">
            {Object.entries(run.prompt_versions)
              .map(([k, v]) => `${k}=${String(v)}`)
              .join(' · ')}
          </span>
        </div>
      )}
      {metricChips(run).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {metricChips(run).map(([k, v]) => (
            <span
              key={k}
              className="rounded-md border border-zinc-950/10 bg-white px-2 py-0.5 font-mono text-xs tabular-nums dark:border-white/10 dark:bg-zinc-900"
            >
              {k}: <span className="font-semibold">{v}</span>
            </span>
          ))}
        </div>
      )}
      <div className="max-h-64 overflow-y-auto rounded-lg border border-zinc-950/10 bg-white p-2 font-mono text-xs dark:border-white/10 dark:bg-zinc-950">
        {(events.data ?? []).length === 0 ?
          <span className="text-zinc-400">Noch keine Ereignisse.</span>
        : (events.data ?? []).map((e) => (
            <div key={e.event_uuid} className="flex gap-2">
              <span className="shrink-0 text-zinc-400">
                {formatTimestamp(e.ts)}
              </span>
              <span>{e.message}</span>
            </div>
          ))
        }
      </div>
    </div>
  );
}

function StartDialog({
  projectUuid,
  open,
  onClose,
}: {
  projectUuid: string;
  open: boolean;
  onClose: () => void;
}) {
  const enqueue = useEnqueueEvalRun();
  const [kind, setKind] = useState<EvalRun['kind']>('calculator_gold');
  const [absTol, setAbsTol] = useState('0');
  const [limit, setLimit] = useState('');

  const start = () => {
    const params: Record<string, string | number> = { abs_tol: absTol || '0' };
    if (kind === 'calculator_gold' && limit) params.limit = Number(limit);
    const body: EvalRunCreate = {
      kind,
      params,
      ...(kind === 'calculator_gold' ? { project_uuid: projectUuid } : {}),
    };
    enqueue.mutate(body, { onSuccess: onClose });
  };

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>Evaluation starten</DialogTitle>
      <DialogBody className="flex flex-col gap-4">
        <Field>
          <Label>Art</Label>
          <Select
            value={kind}
            onChange={(e) => setKind(e.target.value as EvalRun['kind'])}
          >
            {STARTABLE_KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field>
            <Label>Toleranz (abs_tol)</Label>
            <Input
              value={absTol}
              onChange={(e) => setAbsTol(e.target.value)}
              placeholder="0"
            />
          </Field>
          {kind === 'calculator_gold' && (
            <Field>
              <Label>Limit (Positionen)</Label>
              <Input
                type="number"
                min={1}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                placeholder="alle"
              />
            </Field>
          )}
        </div>
        {kind === 'calculator_gold' ?
          <Text className="text-xs">
            Bewertet jede Gold-Position dieses Projekts mit den aktuellen
            Prompts (braucht erfasstes Gold und das ingestierte Projekt).
          </Text>
        : <Text className="text-xs">
            Bewertet die EKT_CHAT_VALUES-Extraktion gegen die Fixture-Datei —
            projektunabhängig, braucht nur den Prompt und OpenRouter.
          </Text>
        }
        {enqueue.isError && (
          <Text className="text-xs text-red-600 dark:text-red-400">
            {(enqueue.error as Error).message}
          </Text>
        )}
      </DialogBody>
      <DialogActions>
        <Button plain onClick={onClose}>
          Abbrechen
        </Button>
        <Button onClick={start} disabled={enqueue.isPending}>
          <PlayIcon />
          Starten
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function RunsTab({ projectUuid }: { projectUuid: string }) {
  const runs = useEvalRuns();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (runs.isLoading) return <LoadingState />;

  // This project's runs plus project-free ones (chat_values grades the same prompts).
  const rows = (runs.data ?? []).filter(
    (r) => r.project_uuid === projectUuid || r.project_uuid == null,
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <Text className="text-xs">
          Läufe führt der Worker aus (gleiche Warteschlangen-Mechanik wie die
          Ingestion); Ergebnisse sind auf die Prompt-Versionen des Laufs
          geschlüsselt.
        </Text>
        <Button onClick={() => setDialogOpen(true)}>
          <PlayIcon />
          Evaluation starten
        </Button>
      </div>

      {rows.length === 0 ?
        <Text className="text-sm">Noch keine Läufe.</Text>
      : <Table className="[--gutter:--spacing(4)]">
          <TableHead>
            <TableRow>
              <TableHeader className="w-8" />
              <TableHeader>Art</TableHeader>
              <TableHeader>Status</TableHeader>
              <TableHeader>Gestartet</TableHeader>
              <TableHeader>Versuche</TableHeader>
              <TableHeader>Ergebnis</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((run) => {
              const expanded = expandedId === run.eval_run_uuid;
              const chips = metricChips(run);
              return (
                <Fragment key={run.eval_run_uuid}>
                  <TableRow
                    className="cursor-pointer"
                    onClick={() =>
                      setExpandedId(expanded ? null : run.eval_run_uuid)
                    }
                  >
                    <TableCell>
                      <ChevronRightIcon
                        className={clsx(
                          'h-4 w-4 text-zinc-400 transition-transform',
                          expanded && 'rotate-90',
                        )}
                      />
                    </TableCell>
                    <TableCell className="font-medium">
                      {KIND_LABEL[run.kind]}
                    </TableCell>
                    <TableCell>
                      <Badge color={STATUS_BADGE[run.status]}>
                        {run.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-zinc-500">
                      {formatRelativeTime(run.created_at)}
                    </TableCell>
                    <TableCell className="text-zinc-500 tabular-nums">
                      {run.attempts}
                    </TableCell>
                    <TableCell className="max-w-96">
                      {run.status === 'failed' ?
                        <span className="truncate text-xs text-red-600 dark:text-red-400">
                          {run.error}
                        </span>
                      : chips.length > 0 ?
                        <span className="font-mono text-xs text-zinc-500 tabular-nums">
                          {chips
                            .slice(0, 3)
                            .map(([k, v]) => `${k} ${v}`)
                            .join(' · ')}
                        </span>
                      : <span className="text-zinc-400">—</span>}
                    </TableCell>
                  </TableRow>
                  {expanded && (
                    <TableRow>
                      <TableCell
                        colSpan={6}
                        className="bg-zinc-50 dark:bg-zinc-900/50"
                      >
                        <RunDetails run={run} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      }

      <StartDialog
        projectUuid={projectUuid}
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
      />
    </div>
  );
}
