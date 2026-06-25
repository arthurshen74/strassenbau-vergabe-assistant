// Confirm and remove a project and everything under it. The delete cascades server-side to the
// project's documents (thumbnails, source lines, LV items, ingest jobs), conversations,
// object-storage blobs, and Elasticsearch chunks.

import { useState } from 'react';
import { useDeleteProject } from '../../api/projects';
import {
  Alert,
  AlertActions,
  AlertDescription,
  AlertTitle,
} from '../../components/ui/alert';
import { Button } from '../../components/ui/button';

export function DeleteProjectDialog({
  projectUuid,
  projectName,
  open,
  onClose,
  onDeleted,
}: {
  projectUuid: string;
  projectName: string;
  open: boolean;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const remove = useDeleteProject();
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (remove.isPending) return;
    setError(null);
    onClose();
  };

  const confirm = async () => {
    setError(null);
    try {
      await remove.mutateAsync(projectUuid);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Alert open={open} onClose={close} size="lg">
      <AlertTitle>Delete project?</AlertTitle>
      <AlertDescription>
        {`"${projectName}" and everything under it — all documents, extracted LV items, thumbnails, conversations, object-storage files, and search index entries — will be permanently removed. This cannot be undone.`}
      </AlertDescription>
      {error && <div className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</div>}
      <AlertActions>
        <Button plain onClick={close} disabled={remove.isPending}>
          Cancel
        </Button>
        <Button color="red" onClick={confirm} disabled={remove.isPending}>
          {remove.isPending ? 'Deleting…' : 'Delete project'}
        </Button>
      </AlertActions>
    </Alert>
  );
}
