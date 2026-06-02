// Project Details body: header fields + document list + "Ingest New Document".

import { useState } from 'react';
import { ArrowLeftIcon, PlusIcon, TrashIcon } from '@heroicons/react/16/solid';
import { useProject, useProjectDocuments } from '../../api/projects';
import { useProjectIngestStatus } from '../../api/ingest';
import type { DocumentRead } from '../../types/generated';
import { IngestStatusCell } from './IngestStatusCell';
import { IngestButton } from './IngestButton';
import { Heading } from '../../components/ui/heading';
import { Text } from '../../components/ui/text';
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
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { formatRelativeTime } from '../../lib/format';
import { UploadDocumentDialog } from './UploadDocumentDialog';
import { DeleteDocumentDialog } from './DeleteDocumentDialog';

function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
      <span className="text-sm text-zinc-900 dark:text-zinc-100">{value || '—'}</span>
    </div>
  );
}

export function ProjectDetails({
  projectUuid,
  onBack,
}: {
  projectUuid: string;
  onBack: () => void;
}) {
  const project = useProject(projectUuid);
  const documents = useProjectDocuments(projectUuid);
  const ingestStatus = useProjectIngestStatus(projectUuid);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [docToDelete, setDocToDelete] = useState<DocumentRead | null>(null);

  if (project.isPending) return <LoadingState label="Loading project…" />;
  if (project.isError) {
    return <ErrorState message={(project.error as Error).message} onRetry={() => project.refetch()} />;
  }
  const p = project.data;
  const docs = documents.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Button plain onClick={onBack} aria-label="Back">
          <ArrowLeftIcon />
        </Button>
        <Heading level={4}>{p.project_name}</Heading>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <FieldRow label="Vergabe ProjectID" value={p.vergabe_id} />
        <FieldRow label="Vergabe Stelle" value={p.vergabestelle} />
        <FieldRow label="Location" value={p.location ?? ''} />
        <FieldRow label="Documents" value={String(docs.length)} />
      </div>
      {p.project_description && <Text>{p.project_description}</Text>}

      <div className="flex items-center justify-between">
        <Heading level={5}>Documents</Heading>
        <Button onClick={() => setUploadOpen(true)}>
          <PlusIcon />
          Ingest New Document
        </Button>
      </div>

      {docs.length === 0 ? (
        <Text>No documents yet.</Text>
      ) : (
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader>File</TableHeader>
              <TableHeader>Type</TableHeader>
              <TableHeader>Status</TableHeader>
              <TableHeader>Pages</TableHeader>
              <TableHeader>Added</TableHeader>
              <TableHeader className="relative w-0">
                <span className="sr-only">Actions</span>
              </TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {docs.map((d) => (
              <TableRow key={d.document_uuid}>
                <TableCell className="font-medium">{d.file_name}</TableCell>
                <TableCell>
                  <Badge color={d.document_type === 'LV_DOCUMENT' ? 'amber' : 'zinc'}>
                    {d.document_type}
                  </Badge>
                </TableCell>
                <TableCell>
                  <IngestStatusCell status={ingestStatus[d.document_uuid]} />
                </TableCell>
                <TableCell>{d.number_of_pages}</TableCell>
                <TableCell className="text-zinc-500">{formatRelativeTime(d.created_at)}</TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center justify-end gap-1">
                    <IngestButton
                      projectUuid={projectUuid}
                      documentUuid={d.document_uuid}
                      active={
                        ingestStatus[d.document_uuid]?.status === 'queued' ||
                        ingestStatus[d.document_uuid]?.status === 'running'
                      }
                    />
                    <Button
                      plain
                      onClick={() => setDocToDelete(d)}
                      aria-label={`Remove ${d.file_name}`}
                    >
                      <TrashIcon />
                    </Button>
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <UploadDocumentDialog
        projectUuid={projectUuid}
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
      />

      <DeleteDocumentDialog
        projectUuid={projectUuid}
        document={docToDelete}
        open={docToDelete !== null}
        onClose={() => setDocToDelete(null)}
      />
    </div>
  );
}
