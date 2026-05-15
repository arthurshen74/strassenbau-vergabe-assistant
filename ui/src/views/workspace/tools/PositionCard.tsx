// Read-only card showing the current version of a position. Used by
// `add_position`, `modify_position`, and `view_position` tool results.
//
// Edit mode: clicking "Edit" swaps the body for a <PositionForm>
// pre-filled with the current version. On successful modify we keep
// the updated DTO in local state so the inline card reflects the new
// version immediately, even though the original `data` prop is the
// frozen tool-output payload from when the call ran. We don't refetch
// `usePosition(id)` on every render — that'd cost a network call per
// position card in the chat history.
//
// We hide Edit on archived positions: editing is for active roles, and
// reactivating-by-edit would muddy the lifecycle.

import { useState } from 'react';
import type {
  PositionDTO,
  PositionFieldsBody,
  PositionVersionDTO,
} from '../../../types/generated';
import { Heading } from '../../../components/ui/heading';
import { Text } from '../../../components/ui/text';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { ArrowLeftIcon, PencilSquareIcon } from '@heroicons/react/16/solid';
import { formatRelativeTime, formatSalaryRange } from '../../../lib/format';
import { useModifyPosition } from '../../../api/positions';
import { ApiError } from '../../../api/client';
import { PositionForm } from './PositionForm';

const LEVEL_COLOR: Record<
  PositionVersionDTO['level'],
  'zinc' | 'blue' | 'purple' | 'amber'
> = {
  junior: 'zinc',
  mid: 'blue',
  senior: 'purple',
  staff: 'amber',
};

const PROFICIENCY_COLOR: Record<
  PositionVersionDTO['skills'][number]['proficiency'],
  'zinc' | 'blue' | 'green' | 'purple'
> = {
  novice: 'zinc',
  practitioner: 'blue',
  advanced: 'green',
  expert: 'purple',
};

export interface PositionCardProps {
  data: PositionDTO;
  /** Header label depends on which tool produced this result. */
  variant?: 'view' | 'created' | 'modified';
  /** When provided, a back button is shown so the user can return to the list. */
  onBack?: () => void;
  /** When true, the card opens directly in edit mode (e.g. Edit clicked from list). */
  initialEditing?: boolean;
}

function currentVersion(p: PositionDTO): PositionVersionDTO {
  return (
    p.versions.find((v) => v.version === p.current_version) ??
    p.versions[p.versions.length - 1]
  );
}

const VARIANT_HEADING: Record<
  NonNullable<PositionCardProps['variant']>,
  string
> = {
  view: 'Position',
  created: 'Position created',
  modified: 'Position updated',
};

export function PositionCard({ data, variant = 'view', onBack, initialEditing }: PositionCardProps) {
  // The DTO we actually display. Starts as the prop and can be
  // overridden by a successful modify so the card self-updates without
  // forcing a re-fetch.
  const [override, setOverride] = useState<PositionDTO | null>(null);
  const display = override ?? data;
  const v = currentVersion(display);

  const [editing, setEditing] = useState(initialEditing ?? false);
  const [serverError, setServerError] = useState<string | null>(null);
  const modify = useModifyPosition(display.id);

  const handleSave = async (body: PositionFieldsBody) => {
    setServerError(null);
    try {
      // PositionFieldsBody is a superset of ModifyPositionBody (every
      // field present, all required ones non-null). We send every field
      // so the new version is fully specified — the server only persists
      // a NEW version anyway, so "send only what changed" isn't a
      // material savings here.
      const updated = await modify.mutateAsync(body);
      setOverride(updated);
      setEditing(false);
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
        <PositionForm
          initialVersion={v}
          heading={`Edit ${v.title}`}
          submitLabel="Save changes"
          submitting={modify.isPending}
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

  const salary = formatSalaryRange(v.salary_min, v.salary_max);
  // Choose the heading that's most truthful right now. If we've edited
  // the card after the original tool result, switch to "modified" so
  // the user doesn't see "Position created" stuck on a now-edited card.
  const heading = override
    ? VARIANT_HEADING.modified
    : VARIANT_HEADING[variant];

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
        <div className="flex items-center gap-1">
          <Badge color={LEVEL_COLOR[v.level]}>{v.level}</Badge>
          <Badge color="zinc">v{v.version}</Badge>
          {display.archived && <Badge color="zinc">archived</Badge>}
          {!display.archived && (
            <Button
              plain
              onClick={() => setEditing(true)}
              aria-label="Edit position"
              title="Edit this position"
            >
              <PencilSquareIcon />
              Edit
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <Text className="text-base font-medium text-zinc-900 dark:text-zinc-100">
          {v.title}
        </Text>
        <Text className="text-xs">
          {v.company} · {v.department}
          {v.remote ? ' · Remote' : v.location ? ` · ${v.location}` : ''}
          {salary && ` · ${salary}`}
        </Text>
      </div>

      {v.skills.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {v.skills.map((s, i) => (
            <Badge key={`${s.skill}-${i}`} color={PROFICIENCY_COLOR[s.proficiency]}>
              {s.skill} · {s.proficiency}
            </Badge>
          ))}
        </div>
      )}

      {v.description && (
        <Text className="text-sm text-zinc-700 dark:text-zinc-300">
          {v.description}
        </Text>
      )}

      {v.notes && (
        <Text className="text-xs italic text-zinc-500 dark:text-zinc-400">
          Notes: {v.notes}
        </Text>
      )}

      {display.versions.length > 1 && (
        <details className="mt-1 rounded border border-zinc-950/5 px-3 py-2 dark:border-white/10">
          <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
            View history ({display.versions.length} versions)
          </summary>
          <ul className="mt-2 flex flex-col gap-1 text-xs text-zinc-600 dark:text-zinc-400">
            {[...display.versions]
              .sort((a, b) => b.version - a.version)
              .map((ver) => (
                <li
                  key={ver.version}
                  className="flex items-center justify-between gap-2"
                >
                  <span>
                    v{ver.version} · {ver.title} · {ver.level}
                  </span>
                  <span>{formatRelativeTime(ver.created_at)}</span>
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
