// Upload one or more documents (PDF, or a flat ZIP of files) into a project.
// The document type is auto-assigned from each filename: a PDF named like
// "<name>_LV<x>.pdf" is an LV document, everything else is prose. ZIP entries
// are recorded as PROSE_DOCUMENT server-side.

import { useState } from 'react';
import { useUploadDocuments } from '../../api/projects';
import { DOCUMENT_TYPE_LV, classifyDocumentType } from '../../lib/documentType';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../components/ui/dialog';
import { Field, Label } from '../../components/ui/fieldset';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';

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
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Dialog open={open} onClose={close} size="md">
      <DialogTitle>Ingest New Document</DialogTitle>
      <DialogBody className="flex flex-col gap-4">
        <Field>
          <Label>Files (PDF or a .zip of files)</Label>
          <input
            type="file"
            accept=".pdf,.zip"
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="mt-2 block w-full text-sm text-zinc-700 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm hover:file:bg-zinc-200 dark:text-zinc-300 dark:file:bg-zinc-800"
          />
        </Field>
        {files.length > 0 && (
          <Field>
            <Label>Auto-assigned document type</Label>
            <ul className="mt-2 flex flex-col gap-1.5">
              {files.map((f, i) => {
                const type = classifyDocumentType(f.name);
                return (
                  <li
                    key={`${f.name}-${i}`}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="truncate text-zinc-700 dark:text-zinc-300">
                      {f.name}
                    </span>
                    <Badge color={type === DOCUMENT_TYPE_LV ? 'indigo' : 'zinc'}>
                      {type}
                    </Badge>
                  </li>
                );
              })}
            </ul>
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
