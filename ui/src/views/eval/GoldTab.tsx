// The Kalkulation-Gold tab: gold rows with staleness badges, one expandable
// inline editor at a time, and delete with confirm. Capture stays in Gate B;
// this tab is for curation (prüfen, korrigieren, löschen, neu bestätigen).

import { Fragment, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRightIcon, TrashIcon } from '@heroicons/react/16/solid';
import clsx from 'clsx';
import {
  useDeleteGroundTruth,
  useGroundTruthList,
  useUpsertGroundTruth,
} from '../../api/groundTruth';
import { Alert, AlertActions, AlertDescription, AlertTitle } from '../../components/ui/alert';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
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
import { ErrorState } from '../../components/feedback/ErrorState';
import { formatRelativeTime } from '../../lib/format';
import type { GroundTruthRead, GroundTruthUpsert } from '../../types/generated';
import { GoldVariablesEditor } from './GoldVariablesEditor';

const ART_EINGABE = 'eingabe';

export function GoldTab({ projectUuid }: { projectUuid: string }) {
  const gold = useGroundTruthList(projectUuid);
  const upsert = useUpsertGroundTruth(projectUuid);
  const remove = useDeleteGroundTruth(projectUuid);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<GroundTruthRead | null>(null);

  if (gold.isLoading) return <LoadingState />;
  if (gold.isError) {
    return (
      <ErrorState
        message={(gold.error as Error).message}
        onRetry={() => gold.refetch()}
      />
    );
  }

  const rows = gold.data ?? [];
  if (rows.length === 0) {
    return (
      <Text className="text-sm">
        Noch kein Gold erfasst. Der Erfassungsweg ist Gate B: bei der
        Variablen-Prüfung „Als Ground Truth speichern" anhaken.
      </Text>
    );
  }

  const toggle = (row: GroundTruthRead) => {
    upsert.reset();
    setExpandedId(expandedId === row.lv_item_uuid ? null : row.lv_item_uuid);
  };

  const save = (row: GroundTruthRead, body: GroundTruthUpsert) => {
    upsert.mutate({ lvItemUuid: row.lv_item_uuid, body });
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.lv_item_uuid, {
      onSuccess: () => {
        if (expandedId === deleteTarget.lv_item_uuid) setExpandedId(null);
        setDeleteTarget(null);
      },
    });
  };

  return (
    <>
      <Table className="[--gutter:--spacing(4)]">
        <TableHead>
          <TableRow>
            <TableHeader className="w-8" />
            <TableHeader>OZ</TableHeader>
            <TableHeader>Leistung</TableHeader>
            <TableHeader>Bauverfahren</TableHeader>
            <TableHeader>Variablen</TableHeader>
            <TableHeader>Quelle</TableHeader>
            <TableHeader>Aktualisiert</TableHeader>
            <TableHeader>Status</TableHeader>
            <TableHeader className="w-12" />
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => {
            const expanded = expandedId === row.lv_item_uuid;
            const names = Object.keys(row.gold_variables);
            const eingabe = Object.values(row.gold_variables).filter(
              (v) => v.art === ART_EINGABE,
            ).length;
            return (
              <Fragment key={row.lv_item_uuid}>
                <TableRow
                  className="cursor-pointer"
                  onClick={() => toggle(row)}
                >
                  <TableCell>
                    <ChevronRightIcon
                      className={clsx(
                        'h-4 w-4 text-zinc-400 transition-transform',
                        expanded && 'rotate-90',
                      )}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-zinc-500">
                    {row.oz ?? '—'}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {row.leistung_key}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {row.bauverfahren_key ?? '—'}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {names.length}{' '}
                    <span className="text-xs text-zinc-500">
                      ({eingabe} EINGABE)
                    </span>
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {row.source_conversation_uuid ?
                      <Link
                        to={`/c/${row.source_conversation_uuid}`}
                        className="text-sm text-blue-600 hover:underline dark:text-blue-400"
                      >
                        Konversation
                      </Link>
                    : <span className="text-zinc-400">—</span>}
                  </TableCell>
                  <TableCell className="text-zinc-500">
                    {formatRelativeTime(row.updated_at)}
                  </TableCell>
                  <TableCell>
                    {row.stale ?
                      <Badge color="amber">Veraltet</Badge>
                    : <Badge color="lime">Aktuell</Badge>}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Button
                      plain
                      aria-label="Gold löschen"
                      onClick={() => setDeleteTarget(row)}
                    >
                      <TrashIcon />
                    </Button>
                  </TableCell>
                </TableRow>
                {expanded && (
                  <TableRow>
                    <TableCell colSpan={9} className="bg-zinc-50 dark:bg-zinc-900/50">
                      <GoldVariablesEditor
                        key={`${row.lv_item_uuid}:${row.updated_at}`}
                        row={row}
                        saving={upsert.isPending}
                        errorMessage={
                          upsert.isError ? (upsert.error as Error).message : null
                        }
                        onSave={(body) => save(row, body)}
                      />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>

      <Alert open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <AlertTitle>Gold löschen?</AlertTitle>
        <AlertDescription>
          Position {deleteTarget?.oz ?? deleteTarget?.lv_item_uuid} wird aus dem
          Gold-Set entfernt. Die Korrekturen-Historie bleibt erhalten.
        </AlertDescription>
        <AlertActions>
          <Button plain onClick={() => setDeleteTarget(null)}>
            Abbrechen
          </Button>
          <Button color="red" onClick={confirmDelete} disabled={remove.isPending}>
            Löschen
          </Button>
        </AlertActions>
      </Alert>
    </>
  );
}
