// Upload one or more documents (PDF, GAEB .d83/.x83, or a flat ZIP of files) into a
// project. The server assigns each document's type: each GAEB file becomes a new LV
// document next to any existing ones, a fillable PDF form becomes a form document, and
// everything else (including LV-print PDFs) is prose. The picked files only show their
// format; the real type appears in the documents table after upload. A successful upload
// opens the ingest console filtered to the project.

import { useState } from 'react';
import { useUploadDocuments } from '../../api/projects';
import { useMainWindowStore } from '../../store/mainWindow';
import { GAEB_LV_PATTERN } from '../../lib/documentType';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../components/ui/dialog';
import { Description, Field, Label } from '../../components/ui/fieldset';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import type { IngestConsoleData } from './IngestConsoleView';

export function UploadDocumentDialog({
  projectUuid,
  open,
  onClose,
}: {
  projectUuid: string;
  open: boolean;
  onClose: () => void;
}) {
  const upload = useUploadDocuments(projectUuid);
  const openMainWindow = useMainWindowStore((s) => s.openMainWindow);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (upload.isPending) return;
    setFiles([]);
    setError(null);
    onClose();
  };

  const submit = async () => {
    setError(null);
    try {
      await upload.mutateAsync(files);
      close();
      const data: IngestConsoleData = { projectUuid };
      openMainWindow({ kind: 'ingest_console', data });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Dialog open={open} onClose={close} size="md">
      <DialogTitle>Ingest New Document</DialogTitle>
      <DialogBody className="flex flex-col gap-4">
        <Field>
          <Label>Files (PDF, GAEB .d83/.x83, or a .zip of files)</Label>
          <input
            type="file"
            accept=".pdf,.zip,.d83,.x83"
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="mt-2 block w-full text-sm text-zinc-700 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm hover:file:bg-zinc-200 dark:text-zinc-300 dark:file:bg-zinc-800"
          />
        </Field>
        {files.length > 0 && (
          <Field>
            <Label>Selected files</Label>
            <ul className="mt-2 flex flex-col gap-1.5">
              {files.map((f, i) => {
                const gaeb = GAEB_LV_PATTERN.test(f.name);
                return (
                  <li
                    key={`${f.name}-${i}`}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="truncate text-zinc-700 dark:text-zinc-300">
                      {f.name}
                    </span>
                    <Badge color={gaeb ? 'amber' : 'zinc'}>{gaeb ? 'GAEB' : 'PDF'}</Badge>
                  </li>
                );
              })}
            </ul>
            {files.some((f) => GAEB_LV_PATTERN.test(f.name)) && (
              <Description className="mt-2">
                Each GAEB file becomes its own LV document; existing LV documents are kept.
              </Description>
            )}
          </Field>
        )}
        {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
      </DialogBody>
      <DialogActions>
        <Button plain onClick={close} disabled={upload.isPending}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={files.length === 0 || upload.isPending}>
          {upload.isPending ? 'Uploading…' : 'Upload'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
