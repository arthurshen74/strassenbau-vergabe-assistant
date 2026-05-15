// Inline renderer for `list_prompts`. Compact clickable card per group.
//
// When `interactive` is true, clicking a row fetches the full
// PromptGroupDTO and renders PromptGroupCard inline in the container.
// The list subscribes to live server state so it reflects edits and
// archives without needing a dispatcher round-trip.
//
// When `interactive` is false (historical message snapshots), rows
// render as static summaries with no actions.

import { useState } from 'react';
import type { IPAPrompt, PromptSummaryDTO } from '../../../types/generated';
import { usePrompts, usePromptGroup } from '../../../api/prompts';
import { PromptGroupCard } from './PromptGroupCard';
import { Heading } from '../../../components/ui/heading';
import { Text } from '../../../components/ui/text';
import { Badge } from '../../../components/ui/badge';
import { formatRelativeTime } from '../../../lib/format';
import { LoadingState } from '../../../components/feedback/LoadingState';

interface PromptListProps {
  // The route returns a bare list, but if the wire shape evolves to
  // ``{prompts: [...]}`` we'll keep working.
  data:
    | { prompts: PromptSummaryDTO[] }
    | { result: PromptSummaryDTO[] }
    | PromptSummaryDTO[];
  /**
   * When true, each row is a button that opens PromptGroupCard inline.
   * The list subscribes to live server state to reflect mutations.
   * When false (historical snapshot), rows render as static summaries.
   */
  interactive?: boolean;
}

const TYPE_COLOR: Record<
  PromptSummaryDTO['prompt_type'],
  'zinc' | 'blue' | 'purple' | 'amber' | 'green'
> = {
  dispatcher: 'purple',
  interviewer: 'blue',
  evaluator: 'amber',
  judge: 'green',
  utility: 'zinc',
};

type Selected = { prompt_type: IPAPrompt; name: string } | null;

export function PromptList({ data, interactive }: PromptListProps) {
  const [selected, setSelected] = useState<Selected>(null);
  const liveQuery = usePrompts();
  const groupQuery = usePromptGroup(selected?.prompt_type, selected?.name);

  const propPrompts =
    Array.isArray(data) ? data
    : 'prompts' in data ? data.prompts
    : 'result' in data ? data.result
    : [];

  const prompts =
    interactive && liveQuery.data ? liveQuery.data : propPrompts;

  // Detail view
  if (selected !== null) {
    if (groupQuery.isPending) {
      return <LoadingState label="Loading prompt…" />;
    }
    if (groupQuery.data) {
      return (
        <PromptGroupCard
          data={groupQuery.data}
          variant="view"
          onBack={() => setSelected(null)}
        />
      );
    }
  }

  // List view
  if (prompts.length === 0) {
    return (
      <div className="flex flex-col gap-1">
        <Heading level={4}>Prompts</Heading>
        <Text>No prompts yet.</Text>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Heading level={4}>Prompts ({prompts.length})</Heading>
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2 xl:grid-cols-3">
        {prompts.map((p) => {
          const inner = (
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Text className="font-medium text-zinc-900 dark:text-zinc-100">
                  {p.name}
                </Text>
                <Badge color={TYPE_COLOR[p.prompt_type]}>
                  {p.prompt_type}
                </Badge>
                <Badge color="zinc">v{p.version}</Badge>
                {p.archived && <Badge color="zinc">archived</Badge>}
              </div>
              <Text className="text-xs">{p.model_name}</Text>
              <Text className="text-xs text-zinc-500 dark:text-zinc-400">
                {formatRelativeTime(p.created_at)}
              </Text>
            </div>
          );

          if (interactive) {
            return (
              <button
                key={p.id}
                type="button"
                onClick={() =>
                  setSelected({ prompt_type: p.prompt_type, name: p.name })
                }
                className="flex w-full flex-col gap-2 rounded-md border border-zinc-950/5 p-3 text-left transition-colors hover:bg-zinc-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 dark:border-white/10 dark:hover:bg-white/5 cursor-pointer"
              >
                {inner}
              </button>
            );
          }

          return (
            <div
              key={p.id}
              className="flex flex-col gap-2 rounded-md border border-zinc-950/5 p-3 dark:border-white/10"
            >
              {inner}
            </div>
          );
        })}
      </div>
    </div>
  );
}
