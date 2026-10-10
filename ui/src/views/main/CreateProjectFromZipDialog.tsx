// Create a project from one tender ZIP: the project is named after the ZIP, and every PDF and
// GAEB .d83/.x83 inside it (nested ZIPs included) is queued for ingestion.

import { useState } from 'react';
import type { ProjectFromZipResult } from '../../types/generated';
import { useCreateProjectFromZip } from '../../api/projects';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
} from '../../components/ui/dialog';
import { Field, Label } from '../../components/ui/fieldset';
import { Button } from '../../components/ui/button';

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function CreateProjectFromZipDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (result: ProjectFromZipResult) => void;
}) {
  const create = useCreateProjectFromZip();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setFile(null);
    setError(null);
  };

  const close = () => {
    if (create.isPending) return;
    reset();
    onClose();
  };

  const submit = async () => {
    if (file === null) return;
    setError(null);
    try {
      const result = await create.mutateAsync(file);
      reset();
      onCreated(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Dialog open={open} onClose={close} size="md">
      <DialogTitle>Ingest Project from ZIP</DialogTitle>
      <DialogDescription>
        The project is named after the ZIP. Every PDF and GAEB file inside it, including nested
        ZIPs, is ingested; each GAEB file becomes its own LV document.
      </DialogDescription>
      <DialogBody className="flex flex-col gap-4">
        <Field>
          <Label>Tender ZIP</Label>
          <input
            type="file"
            accept=".zip"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mt-2 block w-full text-sm text-zinc-700 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm hover:file:bg-zinc-200 dark:text-zinc-300 dark:file:bg-zinc-800"
          />
        </Field>
        {file && (
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="truncate text-zinc-700 dark:text-zinc-300">{file.name}</span>
            <span className="shrink-0 text-zinc-500 dark:text-zinc-400">
              {formatSize(file.size)}
            </span>
          </div>
        )}
        {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
      </DialogBody>
      <DialogActions>
        <Button plain onClick={close} disabled={create.isPending}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={file === null || create.isPending}>
          {create.isPending ? 'Uploading…' : 'Create and ingest'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
