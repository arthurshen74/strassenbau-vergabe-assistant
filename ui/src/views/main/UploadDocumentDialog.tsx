// Upload one or more documents (PDF, or a flat ZIP of files) into a project.
// ZIP entries are recorded as PROSE_DOCUMENT server-side regardless of this
// selection; the type applies to a single non-zip file.

import { useState } from 'react';
import { useUploadDocuments } from '../../api/projects';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../components/ui/dialog';
import { Field, Label } from '../../components/ui/fieldset';
import { Select } from '../../components/ui/select';
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
  const [documentType, setDocumentType] = useState('PROSE_DOCUMENT');
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (upload.isPending) return;
    setFiles([]);
    setDocumentType('PROSE_DOCUMENT');
    setError(null);
    onClose();
  };

  const submit = async () => {
    setError(null);
    try {
      await upload.mutateAsync({ files, documentType });
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
        <Field>
          <Label>Document type (single files; ZIP entries become PROSE)</Label>
          <Select value={documentType} onChange={(e) => setDocumentType(e.target.value)}>
            <option value="PROSE_DOCUMENT">PROSE_DOCUMENT</option>
            <option value="LV_DOCUMENT">LV_DOCUMENT</option>
          </Select>
        </Field>
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
