// Projects main-window body: list -> detail / create, navigated by local state.
//
// Dual-sourced like PromptList: `data` (a view_projects tool payload, `{projects:[...]}`
// or a bare array) renders directly; absent, the list fetches via REST.

import { useState } from 'react';
import { PlusIcon } from '@heroicons/react/16/solid';
import type { ProjectRead } from '../../types/generated';
import { useProjects } from '../../api/projects';
import { Heading } from '../../components/ui/heading';
import { Text } from '../../components/ui/text';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { CreateProjectForm } from './CreateProjectForm';
import { ProjectDetails } from './ProjectDetails';

type View = { mode: 'list' } | { mode: 'create' } | { mode: 'detail'; id: string };

function normalize(data: unknown): ProjectRead[] | null {
  if (data == null) return null;
  if (Array.isArray(data)) return data as ProjectRead[];
  if (typeof data === 'object' && 'projects' in (data as Record<string, unknown>)) {
    const p = (data as { projects: unknown }).projects;
    return Array.isArray(p) ? (p as ProjectRead[]) : [];
  }
  return [];
}

export function ProjectsView({ data }: { data?: unknown }) {
  const [view, setView] = useState<View>({ mode: 'list' });

  if (view.mode === 'create') {
    return (
      <CreateProjectForm
        onBack={() => setView({ mode: 'list' })}
        onCreated={(p) => setView({ mode: 'detail', id: p.project_uuid })}
      />
    );
  }
  if (view.mode === 'detail') {
    return <ProjectDetails projectUuid={view.id} onBack={() => setView({ mode: 'list' })} />;
  }
  return (
    <ProjectListBody
      data={data}
      onOpen={(id) => setView({ mode: 'detail', id })}
      onNew={() => setView({ mode: 'create' })}
    />
  );
}

function ProjectListBody({
  data,
  onOpen,
  onNew,
}: {
  data?: unknown;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  const provided = normalize(data);
  const query = useProjects();

  if (provided === null) {
    if (query.isPending) return <LoadingState label="Loading projects…" />;
    if (query.isError) {
      return (
        <ErrorState message={(query.error as Error).message} onRetry={() => query.refetch()} />
      );
    }
  }
  const projects = provided ?? query.data ?? [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <Heading level={4}>Projects ({projects.length})</Heading>
        <Button onClick={onNew}>
          <PlusIcon />
          Ingest New Project
        </Button>
      </div>
      {projects.length === 0 ? (
        <Text>No projects yet.</Text>
      ) : (
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-2 xl:grid-cols-3">
          {projects.map((p) => (
            <button
              key={p.project_uuid}
              type="button"
              onClick={() => onOpen(p.project_uuid)}
              className="flex w-full flex-col gap-1 rounded-md border border-zinc-950/5 p-3 text-left transition-colors hover:bg-zinc-50 dark:border-white/10 dark:hover:bg-white/5"
            >
              <Text className="font-medium text-zinc-900 dark:text-zinc-100">
                {p.project_name}
              </Text>
              <div className="flex flex-wrap items-center gap-2">
                <Badge color="blue">{p.vergabe_id}</Badge>
                {p.location && <Badge color="zinc">{p.location}</Badge>}
              </div>
              <Text className="text-xs text-zinc-500 dark:text-zinc-400">{p.vergabestelle}</Text>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
