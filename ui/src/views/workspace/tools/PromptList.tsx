// Renders the latest version of each configured prompt.
//
// Dual-sourced: when `data` is supplied (a dispatcher `view_prompts` tool
// result, shaped `{prompts: [...]}` or a bare array) it renders that; when
// absent (opened from the sidebar command) it fetches GET /prompts itself.

import { useState } from 'react';
import type { PromptVersionRead } from '../../../types/generated';
import { usePromptsLatest } from '../../../api/prompts';
import { Heading } from '../../../components/ui/heading';
import { Text } from '../../../components/ui/text';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { formatRelativeTime } from '../../../lib/format';
import { LoadingState } from '../../../components/feedback/LoadingState';
import { ErrorState } from '../../../components/feedback/ErrorState';
import { PromptEditDialog } from './PromptEditDialog';
import { PromptImportDialog } from './PromptImportDialog';

type BadgeColor = 'zinc' | 'blue' | 'purple' | 'amber' | 'green' | 'sky' | 'rose';

const TYPE_COLOR: Record<PromptVersionRead['prompt_type'], BadgeColor> = {
  dispatcher: 'purple',
  project_chat: 'blue',
  classify_project_chat_user_message: 'amber',
  multi_question_generator: 'green',
  lv_extraction: 'sky',
  conversation_name: 'rose',
};

// The route returns a bare array; the dispatcher tool returns `{prompts: [...]}`.
function normalize(data: unknown): PromptVersionRead[] | null {
  if (data == null) return null;
  if (Array.isArray(data)) return data as PromptVersionRead[];
  if (typeof data === 'object' && 'prompts' in (data as Record<string, unknown>)) {
    const prompts = (data as { prompts: unknown }).prompts;
    return Array.isArray(prompts) ? (prompts as PromptVersionRead[]) : [];
  }
  return [];
}

export function PromptList({ data }: { data?: unknown }) {
  const provided = normalize(data);
  const query = usePromptsLatest();
  const [editing, setEditing] = useState<PromptVersionRead | null>(null);
  const [importing, setImporting] = useState(false);

  if (provided === null) {
    if (query.isPending) return <LoadingState label="Loading prompts…" />;
    if (query.isError) {
      return (
        <ErrorState
          message={(query.error as Error).message}
          onRetry={() => query.refetch()}
        />
      );
    }
  }

  const prompts = provided ?? query.data ?? [];

  if (prompts.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <Heading level={4}>Prompts</Heading>
          <Button outline onClick={() => setImporting(true)} className="text-xs">
            Import .prompt
          </Button>
        </div>
        <Text>No prompts yet.</Text>
        {importing && (
          <PromptImportDialog open={importing} onClose={() => setImporting(false)} />
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Heading level={4}>Prompts ({prompts.length})</Heading>
        <Button outline onClick={() => setImporting(true)} className="text-xs">
          Import .prompt
        </Button>
      </div>
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2 xl:grid-cols-3">
        {prompts.map((p) => (
          <div
            key={p.prompt_version_uuid}
            className="flex flex-col gap-2 rounded-md border border-zinc-950/5 p-3 dark:border-white/10"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge color={TYPE_COLOR[p.prompt_type]}>{p.prompt_type}</Badge>
              <Badge color="zinc">v{p.version}</Badge>
              <Button plain onClick={() => setEditing(p)} className="ml-auto text-xs">
                Edit
              </Button>
            </div>
            <Text className="text-xs">{p.model_name}</Text>
            <div className="flex flex-wrap gap-2 text-xs text-zinc-500 dark:text-zinc-400">
              {p.temperature != null && <span>temp {p.temperature}</span>}
              {p.top_p != null && <span>top_p {p.top_p}</span>}
              <span>{formatRelativeTime(p.created_at)}</span>
            </div>
            <details className="text-xs">
              <summary className="cursor-pointer text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
                System prompt
              </summary>
              <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-2 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                {p.system_prompt}
              </pre>
            </details>
          </div>
        ))}
      </div>
      {editing && (
        <PromptEditDialog
          prompt={editing}
          open={editing !== null}
          onClose={() => setEditing(null)}
        />
      )}
      {importing && (
        <PromptImportDialog open={importing} onClose={() => setImporting(false)} />
      )}
    </div>
  );
}
