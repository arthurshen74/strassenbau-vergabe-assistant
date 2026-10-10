// Project Details body: header fields + document list + "Ingest New Document".

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeftIcon,
  BeakerIcon,
  ChartBarIcon,
  ChatBubbleLeftRightIcon,
  DocumentArrowDownIcon,
  MagnifyingGlassIcon,
  PencilSquareIcon,
  TrashIcon,
} from "@heroicons/react/16/solid";
import {
  DocumentDuplicateIcon,
  DocumentTextIcon,
  GlobeAltIcon,
  ListBulletIcon,
} from "@heroicons/react/20/solid";
import { useProject, useProjectDocuments } from "../../api/projects";
import { useProjectIngestStatus } from "../../api/ingest";
import { useStartProjectChat } from "./useStartProjectChat";
import { useMainWindowStore } from "../../store/mainWindow";
import { useNlpModalStore } from "../../store/nlpModal";
import { DOCUMENT_TYPE_LV } from "../../lib/documentType";
import type { DocumentRead } from "../../types/generated";
import { IngestStatusCell } from "./IngestStatusCell";
import { IngestButton } from "./IngestButton";
import { Heading } from "../../components/ui/heading";
import { Text } from "../../components/ui/text";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { LoadingState } from "../../components/feedback/LoadingState";
import { ErrorState } from "../../components/feedback/ErrorState";
import { formatRelativeTime } from "../../lib/format";
import { UploadDocumentDialog } from "./UploadDocumentDialog";
import { DeleteDocumentDialog } from "./DeleteDocumentDialog";
import { DeleteProjectDialog } from "./DeleteProjectDialog";
import { EditProjectDialog } from "./EditProjectDialog";
import { DocumentDetailDialog } from "./DocumentDetailDialog";
import { LVItemsTable } from "./LVItemsTable";
import { LVTextsPanel } from "./LVTextsPanel";
import { LvDocumentSelector } from "./LvDocumentSelector";
import { ProjectContextPanel } from "./ProjectContextPanel";
import { ProjectInfoStatus } from "./ProjectInfoStatus";

type ProjectTab = "lv" | "texts" | "documents" | "context";

// Newest first; ties (one upload request) break on document_uuid like the server's LV order.
function newestFirst(a: DocumentRead, b: DocumentRead): number {
  if (a.created_at !== b.created_at)
    return a.created_at < b.created_at ? 1 : -1;
  return a.document_uuid < b.document_uuid ? 1 : -1;
}

function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
      <span className="text-sm text-zinc-900 dark:text-zinc-100">
        {value || "—"}
      </span>
    </div>
  );
}

export function ProjectDetails({
  projectUuid,
  onBack,
}: {
  projectUuid: string;
  onBack: () => void;
}) {
  const project = useProject(projectUuid);
  const documents = useProjectDocuments(projectUuid);
  const ingestStatus = useProjectIngestStatus(projectUuid);
  const startProjectChat = useStartProjectChat();
  const navigate = useNavigate();
  const closeMainWindow = useMainWindowStore((s) => s.closeMainWindow);
  const openNlpAnalysis = useNlpModalStore((s) => s.openNlpAnalysis);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [docToDelete, setDocToDelete] = useState<DocumentRead | null>(null);
  const [docDetail, setDocDetail] = useState<DocumentRead | null>(null);
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [tab, setTab] = useState<ProjectTab>("lv");
  const [selectedLvDocumentUuid, setSelectedLvDocumentUuid] = useState<
    string | null
  >(null);

  if (project.isPending) return <LoadingState label="Loading project…" />;
  if (project.isError) {
    return (
      <ErrorState
        message={(project.error as Error).message}
        onRetry={() => project.refetch()}
      />
    );
  }
  const p = project.data;
  const docs = documents.data ?? [];
  const lvDocuments = docs
    .filter((d) => d.document_type === DOCUMENT_TYPE_LV)
    .sort(newestFirst);
  // Falls back to the newest LV document when nothing is picked or the pick was deleted.
  const selectedLvDocument =
    lvDocuments.find((d) => d.document_uuid === selectedLvDocumentUuid) ??
    lvDocuments[0];

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex shrink-0 flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Button plain onClick={onBack} aria-label="Back">
              <ArrowLeftIcon />
            </Button>
            <Heading level={4}>{p.project_name}</Heading>
            <Button
              plain
              onClick={() => setEditOpen(true)}
              aria-label="Edit project"
            >
              <PencilSquareIcon />
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={() => setUploadOpen(true)}>
              <DocumentArrowDownIcon />
              Ingest New Document
            </Button>
            <Button onClick={() => startProjectChat(projectUuid)}>
              <ChatBubbleLeftRightIcon />
              Chat about this project
            </Button>
            <Button
              outline
              onClick={() => {
                closeMainWindow();
                navigate(`/p/${projectUuid}/eval`);
              }}
            >
              <ChartBarIcon />
              Evaluation
            </Button>
            <Button
              outline
              onClick={() => setDeleteProjectOpen(true)}
              aria-label="Delete project"
            >
              <TrashIcon />
              Delete project
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <FieldRow label="Maßnahmenummer" value={p.massnahmenummer ?? ""} />
          <FieldRow label="Vergabenummer" value={p.vergabe_id ?? ""} />
          <FieldRow label="Bauleistung" value={p.bauleistung ?? ""} />
          <FieldRow label="Vergabestelle" value={p.vergabestelle ?? ""} />
          <FieldRow label="Baustelle" value={p.location ?? ""} />
          <FieldRow label="Documents" value={String(docs.length)} />
        </div>
        {p.project_description && <Text>{p.project_description}</Text>}
        <ProjectInfoStatus projectUuid={projectUuid} />

        <div className="border-b border-zinc-950/10 dark:border-white/10">
          <nav aria-label="Tabs" className="-mb-px flex space-x-8">
            {(
              [
                { id: "lv", name: "LV Positions", icon: ListBulletIcon },
                { id: "texts", name: "LV-Texte", icon: DocumentTextIcon },
                {
                  id: "documents",
                  name: "Documents",
                  icon: DocumentDuplicateIcon,
                },
                { id: "context", name: "Context", icon: GlobeAltIcon },
              ] as const
            ).map((t) => {
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  aria-current={active ? "page" : undefined}
                  className={
                    "group inline-flex items-center border-b-2 px-1 py-3 text-sm font-medium " +
                    (active
                      ? "border-indigo-500 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                      : "border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:border-white/20 dark:hover:text-zinc-300")
                  }
                >
                  <t.icon
                    aria-hidden="true"
                    className={
                      "mr-2 -ml-0.5 size-5 " +
                      (active
                        ? "text-indigo-500 dark:text-indigo-400"
                        : "text-zinc-400 group-hover:text-zinc-500 dark:text-zinc-500")
                    }
                  />
                  <span>{t.name}</span>
                  {t.id === "documents" && lvDocuments.length > 1 && (
                    <Badge color="amber" className="ml-2">
                      {lvDocuments.length} LV
                    </Badge>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
        {(tab === "lv" || tab === "texts") && (
          <LvDocumentSelector
            lvDocuments={lvDocuments}
            selected={selectedLvDocument}
            onChange={setSelectedLvDocumentUuid}
          />
        )}
        {tab === "lv" && (
          <LVItemsTable
            key={selectedLvDocument?.document_uuid}
            projectUuid={projectUuid}
            documentUuid={selectedLvDocument?.document_uuid}
          />
        )}
        {tab === "texts" && (
          <LVTextsPanel
            projectUuid={projectUuid}
            documentUuid={selectedLvDocument?.document_uuid}
          />
        )}

        {tab === "context" && <ProjectContextPanel projectUuid={projectUuid} />}

        {tab === "documents" &&
          (docs.length === 0 ? (
            <Text>No documents yet.</Text>
          ) : (
            <Table dense>
              <TableHead>
                <TableRow>
                  <TableHeader>File</TableHeader>
                  <TableHeader>Type</TableHeader>
                  <TableHeader>Status</TableHeader>
                  <TableHeader>Pages</TableHeader>
                  <TableHeader>Added</TableHeader>
                  <TableHeader className="relative w-0">
                    <span className="sr-only">Actions</span>
                  </TableHeader>
                </TableRow>
              </TableHead>
              <TableBody>
                {docs.map((d) => (
                  <TableRow key={d.document_uuid}>
                    <TableCell
                      className="cursor-pointer font-medium text-zinc-900 hover:text-blue-600 dark:text-zinc-100 dark:hover:text-blue-400"
                      onClick={() => setDocDetail(d)}
                    >
                      <div className="max-w-[350px] whitespace-normal break-words">
                        {d.file_name}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        color={
                          d.document_type === DOCUMENT_TYPE_LV
                            ? "amber"
                            : "zinc"
                        }
                      >
                        {d.document_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <IngestStatusCell
                        status={ingestStatus[d.document_uuid]}
                      />
                    </TableCell>
                    <TableCell
                      className="cursor-pointer hover:text-blue-600 dark:hover:text-blue-400"
                      onClick={() => setDocDetail(d)}
                    >
                      {d.number_of_pages}
                    </TableCell>
                    <TableCell className="text-zinc-500">
                      {formatRelativeTime(d.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="inline-flex items-center justify-end gap-1">
                        <Button
                          plain
                          onClick={() => setDocDetail(d)}
                          aria-label={`Details for ${d.file_name}`}
                        >
                          <MagnifyingGlassIcon />
                        </Button>
                        {d.document_type === "PROSE_DOCUMENT" &&
                          ingestStatus[d.document_uuid]?.status === "done" && (
                            <Button
                              plain
                              onClick={() =>
                                openNlpAnalysis({
                                  kind: "document",
                                  documentUuid: d.document_uuid,
                                  sourceLabel: d.file_name,
                                })
                              }
                              aria-label={`NLP-Analyse for ${d.file_name}`}
                            >
                              <BeakerIcon />
                            </Button>
                          )}
                        <IngestButton
                          projectUuid={projectUuid}
                          documentUuid={d.document_uuid}
                          active={
                            ingestStatus[d.document_uuid]?.status ===
                              "queued" ||
                            ingestStatus[d.document_uuid]?.status === "running"
                          }
                        />
                        <Button
                          plain
                          onClick={() => setDocToDelete(d)}
                          aria-label={`Remove ${d.file_name}`}
                        >
                          <TrashIcon />
                        </Button>
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ))}
      </div>

      <UploadDocumentDialog
        projectUuid={projectUuid}
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
      />

      <DeleteDocumentDialog
        projectUuid={projectUuid}
        document={docToDelete}
        open={docToDelete !== null}
        onClose={() => setDocToDelete(null)}
      />

      <DocumentDetailDialog
        projectUuid={projectUuid}
        document={docDetail}
        open={docDetail !== null}
        onClose={() => setDocDetail(null)}
      />

      {editOpen && (
        <EditProjectDialog project={p} onClose={() => setEditOpen(false)} />
      )}

      <DeleteProjectDialog
        projectUuid={projectUuid}
        projectName={p.project_name}
        open={deleteProjectOpen}
        onClose={() => setDeleteProjectOpen(false)}
        onDeleted={onBack}
      />
    </div>
  );
}
