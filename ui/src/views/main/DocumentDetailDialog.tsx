// Document detail dialog opened from a Projects document row: header metadata plus underline tabs
// for thumbnails, chunks (Simple/LangChain), and the ingestion log (active ∪ archive). A form
// document gets a first tab with its extracted fields and opens on it, since an XFA form's
// thumbnail is only Adobe's placeholder page.

import { useState } from 'react';
import {
  PhotoIcon,
  QueueListIcon,
  Squares2X2Icon,
  TableCellsIcon,
} from '@heroicons/react/20/solid';

import { useDocumentDetail, useDocumentFormFields } from '../../api/documents';
import { Dialog, DialogBody, DialogTitle } from '../../components/ui/dialog';
import { Select } from '../../components/ui/select';
import { Text } from '../../components/ui/text';
import { LoadingState } from '../../components/feedback/LoadingState';
import { formatCost, formatTimestamp } from '../../lib/format';
import { DOCUMENT_TYPE_FORM, formRoleLabel } from '../../lib/documentType';
import { DocumentThumbnailViewer } from './DocumentThumbnailViewer';
import { DocumentChunkViewer } from './DocumentChunkViewer';
import { DocumentActivityLog } from './DocumentActivityLog';
import { FormFieldsTable } from './FormFieldsTable';
import type { DocumentRead } from '../../types/generated';

type Section = 'fields' | 'thumbnails' | 'chunks' | 'log';

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="text-sm text-zinc-900 dark:text-zinc-100">{value}</span>
    </div>
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
  const isForm = document?.document_type === DOCUMENT_TYPE_FORM;
  const [chosen, setSection] = useState<Section | null>(null);
  const section: Section = chosen ?? (isForm ? 'fields' : 'thumbnails');
  const detail = useDocumentDetail(projectUuid, document?.document_uuid);
  const formFields = useDocumentFormFields(
    projectUuid,
    isForm ? document?.document_uuid : undefined,
  );
  const d = detail.data;

  const tabs = d
    ? [
        ...(isForm
          ? [
              {
                id: 'fields' as const,
                name: `Felder (${formFields.data?.length ?? '…'})`,
                icon: TableCellsIcon,
              },
            ]
          : []),
        { id: 'thumbnails' as const, name: `Thumbnails (${d.number_of_pages})`, icon: PhotoIcon },
        {
          id: 'chunks' as const,
          name: isForm
            ? `Chunks (${d.simple_chunk_count})`
            : `Chunks (${d.simple_chunk_count} / ${d.langchain_chunk_count})`,
          icon: Squares2X2Icon,
        },
        { id: 'log' as const, name: 'Ingestion Log', icon: QueueListIcon },
      ]
    : [];

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
              {d.form_role ? (
                <>
                  <Meta label="Formblatt" value={d.form_id ?? '—'} />
                  <Meta label="Rolle" value={formRoleLabel(d.form_role)} />
                </>
              ) : (
                <Meta label="LangChain chunks" value={String(d.langchain_chunk_count)} />
              )}
              <Meta label="Ingestion cost" value={formatCost(d.ingestion_cost)} />
            </div>

            <div>
              <div className="sm:hidden">
                <Select
                  value={section}
                  onChange={(e) => setSection(e.target.value as Section)}
                  aria-label="Select a tab"
                >
                  {tabs.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="hidden sm:block">
                <div className="border-b border-zinc-950/10 dark:border-white/10">
                  <nav aria-label="Tabs" className="-mb-px flex space-x-8">
                    {tabs.map((t) => {
                      const active = section === t.id;
                      return (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => setSection(t.id)}
                          aria-current={active ? 'page' : undefined}
                          className={
                            'group inline-flex items-center border-b-2 px-1 py-3 text-sm font-medium ' +
                            (active
                              ? 'border-indigo-500 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                              : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:border-white/20 dark:hover:text-zinc-300')
                          }
                        >
                          <t.icon
                            aria-hidden="true"
                            className={
                              'mr-2 -ml-0.5 size-5 ' +
                              (active
                                ? 'text-indigo-500 dark:text-indigo-400'
                                : 'text-zinc-400 group-hover:text-zinc-500 dark:text-zinc-500')
                            }
                          />
                          <span>{t.name}</span>
                        </button>
                      );
                    })}
                  </nav>
                </div>
              </div>
            </div>

            {section === 'fields' && <FormFieldsTable query={formFields} />}
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
                simpleOnly={isForm}
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
