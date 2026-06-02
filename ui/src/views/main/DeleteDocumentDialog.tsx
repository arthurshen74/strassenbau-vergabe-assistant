// Confirm and remove a document from a project. The delete cascades server-side
// to the document's thumbnails, source lines, LV items, object-storage blobs, and
// Elasticsearch chunks.

import { useState } from 'react';
import { useDeleteDocument } from '../../api/projects';
import type { DocumentRead } from '../../types/generated';
import {
  Alert,
  AlertActions,
  AlertDescription,
  AlertTitle,
} from '../../components/ui/alert';
import { Button } from '../../components/ui/button';

export function DeleteDocumentDialog({
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
  const remove = useDeleteDocument(projectUuid);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (remove.isPending) return;
    setError(null);
    onClose();
  };

  const confirm = async () => {
    if (!document) return;
    setError(null);
    try {
      await remove.mutateAsync(document.document_uuid);
      close();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Alert open={open} onClose={close} size="md">
      <AlertTitle>Remove document?</AlertTitle>
      <AlertDescription>
        {document
          ? `"${document.file_name}" and everything derived from it (thumbnails, extracted lines, LV items, and search index entries) will be permanently removed. This cannot be undone.`
          : ''}
      </AlertDescription>
      {error && <div className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</div>}
      <AlertActions>
        <Button plain onClick={close} disabled={remove.isPending}>
          Cancel
        </Button>
        <Button color="red" onClick={confirm} disabled={remove.isPending}>
          {remove.isPending ? 'Removing…' : 'Remove'}
        </Button>
      </AlertActions>
    </Alert>
  );
}
