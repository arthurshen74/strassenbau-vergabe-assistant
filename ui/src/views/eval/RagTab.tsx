// The RAG-Fragen tab: curated reference questions with gold answers and
// Fundstellen (document + page). Create/edit inline via RagQuestionEditor;
// questions without refs carry the amber "Referenzen fehlen" badge.

import { Fragment, useState } from 'react';
import { ChevronRightIcon, PlusIcon, TrashIcon } from '@heroicons/react/16/solid';
import clsx from 'clsx';
import { useProjectDocuments } from '../../api/projects';
import {
  useCreateRagGroundTruth,
  useDeleteRagGroundTruth,
  useRagGroundTruthList,
  useUpdateRagGroundTruth,
} from '../../api/ragGroundTruth';
import {
  Alert,
  AlertActions,
  AlertDescription,
  AlertTitle,
} from '../../components/ui/alert';
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
import type { RagGroundTruthRead } from '../../types/generated';
import { RagQuestionEditor } from './RagQuestionEditor';

const TYPE_LABEL: Record<RagGroundTruthRead['question_type'], string> = {
  lookup: 'Lookup',
  aggregation: 'Aggregation',
  multi_hop: 'Multi-Hop',
  constraint_surfacing: 'Constraint-Surfacing',
  cross_doc_conditional: 'Cross-Doc-Conditional',
};

export function RagTab({ projectUuid }: { projectUuid: string }) {
  const questions = useRagGroundTruthList(projectUuid);
  const documents = useProjectDocuments(projectUuid);
  const create = useCreateRagGroundTruth(projectUuid);
  const update = useUpdateRagGroundTruth(projectUuid);
  const remove = useDeleteRagGroundTruth(projectUuid);
  const [adding, setAdding] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RagGroundTruthRead | null>(null);

  if (questions.isLoading || documents.isLoading) return <LoadingState />;
  if (questions.isError) {
    return (
      <ErrorState
        message={(questions.error as Error).message}
        onRetry={() => questions.refetch()}
      />
    );
  }

  const rows = questions.data ?? [];
  const docs = documents.data ?? [];
  const docName = (uuid: string) =>
    docs.find((d) => d.document_uuid === uuid)?.file_name ?? uuid;

  const toggle = (row: RagGroundTruthRead) => {
    update.reset();
    setExpandedId(
      expandedId === row.rag_ground_truth_uuid ? null : row.rag_ground_truth_uuid,
    );
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.rag_ground_truth_uuid, {
      onSuccess: () => {
        if (expandedId === deleteTarget.rag_ground_truth_uuid) setExpandedId(null);
        setDeleteTarget(null);
      },
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <Text className="text-xs">
          Referenzfragen speisen die Retrieval-Metriken (Recall@k, MRR) und die
          Antwort-Bewertung. Referenzen = Fundstellen der Antwort als Dokument +
          Seite.
        </Text>
        {!adding && (
          <Button
            onClick={() => {
              create.reset();
              setAdding(true);
            }}
          >
            <PlusIcon />
            Frage hinzufügen
          </Button>
        )}
      </div>

      {adding && (
        <div className="rounded-lg border border-zinc-950/10 bg-zinc-50 px-4 dark:border-white/10 dark:bg-zinc-900/50">
          <RagQuestionEditor
            initial={null}
            documents={docs}
            saving={create.isPending}
            errorMessage={create.isError ? (create.error as Error).message : null}
            onCancel={() => setAdding(false)}
            onSave={(body) =>
              create.mutate(body, { onSuccess: () => setAdding(false) })
            }
          />
        </div>
      )}

      {rows.length === 0 && !adding ?
        <Text className="text-sm">
          Noch keine Referenzfragen. Mit „Frage hinzufügen" die erste anlegen —
          gute Kandidaten sind Fragen, deren Antwort eindeutig in den Unterlagen
          steht (Fristen, Klassen, Mengen, Abschnitte).
        </Text>
      : rows.length > 0 && (
          <Table className="[--gutter:--spacing(4)]">
            <TableHead>
              <TableRow>
                <TableHeader className="w-8" />
                <TableHeader>Frage</TableHeader>
                <TableHeader>Typ</TableHeader>
                <TableHeader>Antwort</TableHeader>
                <TableHeader>Referenzen</TableHeader>
                <TableHeader>Aktualisiert</TableHeader>
                <TableHeader className="w-12" />
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => {
                const expanded = expandedId === row.rag_ground_truth_uuid;
                const refs = row.refs ?? [];
                return (
                  <Fragment key={row.rag_ground_truth_uuid}>
                    <TableRow className="cursor-pointer" onClick={() => toggle(row)}>
                      <TableCell>
                        <ChevronRightIcon
                          className={clsx(
                            'h-4 w-4 text-zinc-400 transition-transform',
                            expanded && 'rotate-90',
                          )}
                        />
                      </TableCell>
                      <TableCell className="max-w-80 truncate font-medium">
                        {row.question}
                      </TableCell>
                      <TableCell>
                        <Badge color="zinc">{TYPE_LABEL[row.question_type]}</Badge>
                      </TableCell>
                      <TableCell className="max-w-64 truncate text-zinc-500">
                        {row.gold_answer}
                      </TableCell>
                      <TableCell>
                        {refs.length === 0 ?
                          <Badge color="amber">Referenzen fehlen</Badge>
                        : <div className="flex max-w-64 flex-wrap gap-1">
                            {refs.map((r) => (
                              <span
                                key={`${r.document_uuid}:${r.page}`}
                                className="rounded-md border border-blue-500/20 bg-blue-50 px-1.5 py-0.5 font-mono text-[11px] text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
                              >
                                {docName(r.document_uuid)}::S.{r.page}
                              </span>
                            ))}
                          </div>
                        }
                      </TableCell>
                      <TableCell className="text-zinc-500">
                        {formatRelativeTime(row.updated_at)}
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Button
                          plain
                          aria-label="Frage löschen"
                          onClick={() => setDeleteTarget(row)}
                        >
                          <TrashIcon />
                        </Button>
                      </TableCell>
                    </TableRow>
                    {expanded && (
                      <TableRow>
                        <TableCell
                          colSpan={7}
                          className="bg-zinc-50 dark:bg-zinc-900/50"
                        >
                          <RagQuestionEditor
                            key={`${row.rag_ground_truth_uuid}:${row.updated_at}`}
                            initial={row}
                            documents={docs}
                            saving={update.isPending}
                            errorMessage={
                              update.isError ?
                                (update.error as Error).message
                              : null
                            }
                            onCancel={() => setExpandedId(null)}
                            onSave={(body) =>
                              update.mutate({
                                ragGroundTruthUuid: row.rag_ground_truth_uuid,
                                body,
                              })
                            }
                          />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        )
      }

      <Alert open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <AlertTitle>Referenzfrage löschen?</AlertTitle>
        <AlertDescription>
          „{deleteTarget?.question}" wird aus dem Gold-Set entfernt.
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
    </div>
  );
}
