// Confirm and queue a Projektinfo re-run that overwrites the header fields it finds.

import { useState } from "react";
import { useRunProjectInfo } from "../../api/projects";
import {
  Alert,
  AlertActions,
  AlertDescription,
  AlertTitle,
} from "../../components/ui/alert";
import { Button } from "../../components/ui/button";

export function RerunProjectInfoDialog({
  projectUuid,
  open,
  onClose,
}: {
  projectUuid: string;
  open: boolean;
  onClose: () => void;
}) {
  const run = useRunProjectInfo(projectUuid);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (run.isPending) return;
    setError(null);
    onClose();
  };

  const confirm = async () => {
    setError(null);
    try {
      await run.mutateAsync({ overwrite: true });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Alert open={open} onClose={close} size="lg">
      <AlertTitle>Projektinfo neu ermitteln?</AlertTitle>
      <AlertDescription>
        Die Kopffelder werden erneut aus den Vergabeunterlagen gelesen. Jeder
        gefundene Wert überschreibt den aktuellen, auch einen von Hand
        eingetragenen. Nicht gefundene Felder bleiben unverändert.
      </AlertDescription>
      {error && (
        <div className="mt-4 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}
      <AlertActions>
        <Button plain onClick={close} disabled={run.isPending}>
          Abbrechen
        </Button>
        <Button onClick={confirm} disabled={run.isPending}>
          {run.isPending ? "Wird gestartet…" : "Neu ermitteln"}
        </Button>
      </AlertActions>
    </Alert>
  );
}
