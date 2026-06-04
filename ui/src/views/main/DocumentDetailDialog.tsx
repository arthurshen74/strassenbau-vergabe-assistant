// Document detail dialog opened from a Projects document row: header metadata plus three
// sections — thumbnails, chunks (Simple/LangChain), and the ingestion log (active ∪ archive).

import { useState, type ReactNode } from 'react';

import { useDocumentDetail } from '../../api/documents';
import { Dialog, DialogBody, DialogTitle } from '../../components/ui/dialog';
import { Text } from '../../components/ui/text';
import { LoadingState } from '../../components/feedback/LoadingState';
import { formatTimestamp } from '../../lib/format';
import { DocumentThumbnailViewer } from './DocumentThumbnailViewer';
import { DocumentChunkViewer } from './DocumentChunkViewer';
import { DocumentActivityLog } from './DocumentActivityLog';
import type { DocumentRead } from '../../types/generated';

type Section = 'thumbnails' | 'chunks' | 'log';

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="text-sm text-zinc-900 dark:text-zinc-100">{value}</span>
    </div>
  );
}

function Tab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        'rounded-md px-2 py-1 text-sm transition ' +
        (active
          ? 'bg-zinc-100 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
          : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200')
      }
    >
      {children}
    </button>
  );
}

export function DocumentDetailDialog({
  projectUuid,
  document,
  open,
  onClose,
}: {
  projectUuid: string;
  document: DocumentRead | null;
  open: boolean;
  onClose: () => void;
}) {
  const [section, setSection] = useState<Section>('thumbnails');
  const detail = useDocumentDetail(projectUuid, document?.document_uuid);
  const d = detail.data;

  return (
    <Dialog open={open} onClose={onClose} size="5xl">
      <DialogTitle>{document?.file_name ?? 'Document'}</DialogTitle>
      <DialogBody className="flex flex-col gap-4">
        {detail.isPending ? (
          <LoadingState label="Loading document…" />
        ) : d && document ? (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Meta label="Pages" value={String(d.number_of_pages)} />
              <Meta label="Uploaded" value={formatTimestamp(d.upload_date)} />
              <Meta
                label="Last ingested"
                value={d.last_ingest_date ? formatTimestamp(d.last_ingest_date) : '—'}
              />
              <Meta label="SimpleChunks" value={String(d.simple_chunk_count)} />
              <Meta label="LangChain chunks" value={String(d.langchain_chunk_count)} />
            </div>

            <div className="flex gap-2 border-b border-zinc-950/5 pb-2 dark:border-white/5">
              <Tab active={section === 'thumbnails'} onClick={() => setSection('thumbnails')}>
                Thumbnails ({d.number_of_pages})
              </Tab>
              <Tab active={section === 'chunks'} onClick={() => setSection('chunks')}>
                Chunks ({d.simple_chunk_count} / {d.langchain_chunk_count})
              </Tab>
              <Tab active={section === 'log'} onClick={() => setSection('log')}>
                Ingestion Log
              </Tab>
            </div>

            {section === 'thumbnails' && (
              <DocumentThumbnailViewer
                projectUuid={projectUuid}
                documentUuid={document.document_uuid}
                numberOfPages={d.number_of_pages}
              />
            )}
            {section === 'chunks' && (
              <DocumentChunkViewer
                projectUuid={projectUuid}
                documentUuid={document.document_uuid}
              />
            )}
            {section === 'log' && (
              <DocumentActivityLog
                projectUuid={projectUuid}
                documentUuid={document.document_uuid}
              />
            )}
          </>
        ) : (
          <Text>Could not load this document.</Text>
        )}
      </DialogBody>
    </Dialog>
  );
}
