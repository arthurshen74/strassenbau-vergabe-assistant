// Inline renderer for view_prompt / edit_prompt / archive_prompt.
//
// Shows the latest version's metadata and system prompt, with three
// affordances: Edit, Archive, Test. Clicking Edit swaps the body for
// <PromptForm>; clicking Test expands the inline <PromptTester>.
// The history accordion lists every version in descending order; each
// historical version exposes its own Test button so the user can
// compare versions side-by-side over time.
//
// Local override pattern: when an Edit or
// Archive succeeds, we keep the freshly-returned PromptGroupDTO in
// component state so the inline card reflects the new version
// immediately without re-fetching for every card in the chat history.

import { useState } from 'react';
import type {
  EditPromptBody,
  PromptDTO,
  PromptGroupDTO,
} from '../../../types/generated';
import { Heading } from '../../../components/ui/heading';
import { Text } from '../../../components/ui/text';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import {
  ArrowLeftIcon,
  ArchiveBoxIcon,
  BeakerIcon,
  PencilSquareIcon,
} from '@heroicons/react/16/solid';
import { useArchivePrompt, useEditPrompt } from '../../../api/prompts';
import { ApiError } from '../../../api/client';
import { formatRelativeTime } from '../../../lib/format';
import { PromptForm } from './PromptForm';
import { PromptTester } from './PromptTester';

const TYPE_COLOR: Record<
  PromptDTO['prompt_type'],
  'zinc' | 'blue' | 'purple' | 'amber' | 'green'
> = {
  dispatcher: 'purple',
  interviewer: 'blue',
  evaluator: 'amber',
  judge: 'green',
  utility: 'zinc',
};

export interface PromptGroupCardProps {
  data: PromptGroupDTO;
  /** Header label varies by which tool produced this result. */
  variant?: 'view' | 'edited' | 'archived';
  /** When provided, a back button is shown so the user can return to the list. */
  onBack?: () => void;
}

const VARIANT_HEADING: Record<
  NonNullable<PromptGroupCardProps['variant']>,
  string
> = {
  view: 'Prompt',
  edited: 'Prompt updated',
  archived: 'Prompt archived',
};

export function PromptGroupCard({ data, variant = 'view', onBack }: PromptGroupCardProps) {
  const [override, setOverride] = useState<PromptGroupDTO | null>(null);
  const display = override ?? data;
  const latest = display.latest;
  const archived = display.archived;

  const [editing, setEditing] = useState(false);
  const [testing, setTesting] = useState(false);
  // Lets the user expand a specific historical version to test it.
  const [testVersionNumber, setTestVersionNumber] = useState<number | null>(
    null,
  );
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const edit = useEditPrompt(latest.prompt_type, latest.name);
  const archive = useArchivePrompt();

  const heading = override
    ? archived
      ? VARIANT_HEADING.archived
      : VARIANT_HEADING.edited
    : VARIANT_HEADING[variant];

  const handleSave = async (body: EditPromptBody) => {
    setServerError(null);
    try {
      const updated = await edit.mutateAsync(body);
      setOverride(updated);
      setEditing(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? formatApiError(err) : (err as Error).message;
      setServerError(msg);
    }
  };

  const handleArchive = async () => {
    setServerError(null);
    try {
      const updated = await archive.mutateAsync({
        prompt_type: latest.prompt_type,
        name: latest.name,
      });
      setOverride(updated);
    } catch (err) {
      const msg =
        err instanceof ApiError ? formatApiError(err) : (err as Error).message;
      setServerError(msg);
    }
  };

  if (editing) {
    return (
      <div className="flex flex-col gap-3">
        {onBack && (
          <Button plain onClick={onBack} className="self-start">
            <ArrowLeftIcon />
            Back to list
          </Button>
        )}
        <PromptForm
          initialVersion={latest}
          heading={`Edit ${latest.prompt_type}/${latest.name}`}
          submitting={edit.isPending}
          errorMessage={serverError}
          onSubmit={handleSave}
          onCancel={() => {
            setEditing(false);
            setServerError(null);
          }}
        />
      </div>
    );
  }

  // The version selected for testing — defaults to the latest.
  const testVersion: PromptDTO =
    (testVersionNumber != null
      ? display.versions.find((v) => v.version === testVersionNumber)
      : null) ?? latest;

  return (
    <div className="flex flex-col gap-3">
      {onBack && (
        <Button plain onClick={onBack} className="self-start">
          <ArrowLeftIcon />
          Back to list
        </Button>
      )}
      <div className="flex items-center justify-between gap-2">
        <Heading level={4}>{heading}</Heading>
        <div className="flex flex-wrap items-center gap-1">
          <Badge color={TYPE_COLOR[latest.prompt_type]}>
            {latest.prompt_type}
          </Badge>
          <Badge color="zinc">v{latest.version}</Badge>
          {archived && <Badge color="zinc">archived</Badge>}
          {!archived && (
            <>
              <Button
                plain
                onClick={() => {
                  setTestVersionNumber(null);
                  setTesting((t) => !t);
                }}
                aria-label="Test prompt"
                title="Send a message to this prompt"
              >
                <BeakerIcon />
                Test
              </Button>
              <Button
                plain
                onClick={() => setEditing(true)}
                aria-label="Edit prompt"
              >
                <PencilSquareIcon />
                Edit
              </Button>
              <Button
                plain
                onClick={handleArchive}
                disabled={archive.isPending}
                aria-label="Archive prompt"
                title="Archive (soft delete) this prompt"
              >
                <ArchiveBoxIcon />
                Archive
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <Text className="text-base font-medium text-zinc-900 dark:text-zinc-100">
          {latest.prompt_type}/{latest.name}
        </Text>
        <Text className="text-xs">
          {latest.model_name} · temp {latest.temperature} · top_p {latest.top_p}
          {latest.min_p != null && ` · min_p ${latest.min_p}`}
        </Text>
      </div>

      {latest.dimensions && latest.dimensions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {latest.dimensions.map((d) => (
            <Badge key={d.name} color="amber">
              {d.name} · {d.scale_min}–{d.scale_max}
            </Badge>
          ))}
        </div>
      )}

      <details
        open={showSystemPrompt}
        onToggle={(e) =>
          setShowSystemPrompt((e.target as HTMLDetailsElement).open)
        }
        className="rounded border border-zinc-950/5 px-3 py-2 dark:border-white/10"
      >
        <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
          System prompt ({latest.system_prompt.length.toLocaleString()} chars)
        </summary>
        <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-3 text-xs text-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
          {latest.system_prompt}
        </pre>
      </details>

      {serverError && (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-700/50 dark:bg-red-950/30 dark:text-red-300">
          {serverError}
        </div>
      )}

      {testing && <PromptTester version={testVersion} />}

      {display.versions.length > 1 && (
        <details className="rounded border border-zinc-950/5 px-3 py-2 dark:border-white/10">
          <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
            View history ({display.versions.length} versions)
          </summary>
          <ul className="mt-2 flex flex-col gap-1 text-xs text-zinc-600 dark:text-zinc-400">
            {display.versions.map((ver) => (
              <li
                key={ver.version}
                className="flex items-center justify-between gap-2"
              >
                <span>
                  v{ver.version} · {ver.model_name} · temp {ver.temperature}
                </span>
                <div className="flex items-center gap-2">
                  <span>{formatRelativeTime(ver.created_at)}</span>
                  <Button
                    plain
                    onClick={() => {
                      setTestVersionNumber(ver.version);
                      setTesting(true);
                    }}
                  >
                    Test
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function formatApiError(err: ApiError): string {
  const body = err.body as { detail?: unknown } | null;
  if (body && body.detail) {
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: unknown) =>
          typeof d === 'object' && d && 'msg' in d
            ? String((d as { msg: unknown }).msg)
            : String(d),
        )
        .join('; ');
    }
  }
  return err.message;
}
