// Projektinfo status line under the project header: the latest job's state, an expandable
// per-field found/not-found list with the evidence quote, and the re-run button.

import { useState } from "react";
import {
  ArrowPathIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from "@heroicons/react/16/solid";
import { isProjectInfoOpen, useProjectInfo } from "../../api/projects";
import type {
  ProjectInfoJobRead,
  RagQueryVersionRead,
} from "../../types/generated";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { RerunProjectInfoDialog } from "./RerunProjectInfoDialog";

type ProjectInfoKey = RagQueryVersionRead["query_key"];

// Display order and labels; the Record type makes tsc flag a missing key.
const FIELD_LABELS: Record<ProjectInfoKey, string> = {
  "project-name": "Projektname",
  "project-massnahmenummer": "Maßnahmenummer",
  "project-vergabenummer": "Vergabenummer",
  "project-vergabestelle": "Vergabestelle",
  "project-bauleistung": "Bauleistung",
  "project-location": "Baustelle",
  "project-description": "Beschreibung",
};
const FIELD_KEYS = Object.keys(FIELD_LABELS) as ProjectInfoKey[];

function statusText(job: ProjectInfoJobRead): string {
  switch (job.status) {
    case "queued":
      return "wartet auf Ingestion";
    case "running":
      return "läuft";
    case "failed":
      return "fehlgeschlagen";
    case "skipped":
      return "übersprungen";
    case "done": {
      const results = Object.values(job.result ?? {});
      const found = results.filter((r) => r.gefunden).length;
      return `fertig (${found} von ${results.length} gefunden)`;
    }
  }
}

function FieldResults({ job }: { job: ProjectInfoJobRead }) {
  const results = job.result ?? {};
  return (
    <ul className="flex flex-col gap-1 text-xs">
      {FIELD_KEYS.map((key) => {
        const r = results[key];
        if (!r) return null;
        return (
          <li key={key} className="flex items-baseline gap-2">
            <span className="w-28 shrink-0">
              <Badge color={r.gefunden ? "green" : "zinc"}>
                {r.gefunden ? "gefunden" : "nicht gefunden"}
              </Badge>
            </span>
            <span className="w-32 shrink-0 text-zinc-500 dark:text-zinc-400">
              {FIELD_LABELS[key]}
            </span>
            <span
              className="min-w-0 truncate text-zinc-900 dark:text-zinc-100"
              title={r.beleg ? `Beleg: ${r.beleg}` : undefined}
            >
              {r.gefunden ? r.wert : (r.error ?? "—")}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function ProjectInfoStatus({ projectUuid }: { projectUuid: string }) {
  const info = useProjectInfo(projectUuid);
  const [expanded, setExpanded] = useState(false);
  const [rerunOpen, setRerunOpen] = useState(false);
  const job = info.data;
  const canExpand = job?.status === "done";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2 text-sm">
        {job ? (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            disabled={!canExpand}
            className="flex items-center gap-1 text-zinc-600 enabled:hover:text-zinc-900 dark:text-zinc-400 dark:enabled:hover:text-zinc-200"
            title={
              job.status === "failed" ? (job.error ?? undefined) : undefined
            }
          >
            {canExpand &&
              (expanded ? (
                <ChevronDownIcon className="size-4" />
              ) : (
                <ChevronRightIcon className="size-4" />
              ))}
            <span>Projektinfo: {statusText(job)}</span>
          </button>
        ) : (
          <span />
        )}
        <Button
          outline
          onClick={() => setRerunOpen(true)}
          disabled={isProjectInfoOpen(job)}
        >
          <ArrowPathIcon />
          Projektinfo neu ermitteln
        </Button>
      </div>
      {canExpand && expanded && job && <FieldResults job={job} />}
      <RerunProjectInfoDialog
        projectUuid={projectUuid}
        open={rerunOpen}
        onClose={() => setRerunOpen(false)}
      />
    </div>
  );
}
