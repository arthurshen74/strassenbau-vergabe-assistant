// Inline renderer for `list_positions`. Compact card per position.
//
// When `interactive` is true the list syncs with the server and row
// actions execute directly in the component:
//   - clicking the title/company area renders PositionCard inline
//   - the "Edit" button opens PositionCard directly in edit mode
//   - the "Archive" button calls the API and refreshes the list
//
// When `interactive` is false (historical message snapshots) the rows
// render as a static summary with no actions.

import { useState } from 'react';
import type { PositionSummaryDTO } from '../../../types/generated';
import { usePositions, usePosition, useArchivePosition } from '../../../api/positions';
import { PositionCard } from './PositionCard';
import { Heading } from '../../../components/ui/heading';
import { Text } from '../../../components/ui/text';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { ArchiveBoxIcon, PencilSquareIcon } from '@heroicons/react/16/solid';
import { formatRelativeTime } from '../../../lib/format';
import { LoadingState } from '../../../components/feedback/LoadingState';

interface PositionListProps {
  data:
    | { positions: PositionSummaryDTO[] }
    | { result: PositionSummaryDTO[] }
    | PositionSummaryDTO[];
  /**
   * When true, rows are interactive: clicking opens the detail card inline,
   * Edit opens the card in edit mode, and Archive hits the API directly.
   * The list subscribes to live server state so it reflects mutations.
   * When false (historical snapshot), rows render as static summaries.
   */
  interactive?: boolean;
}

const LEVEL_COLOR: Record<
  PositionSummaryDTO['level'],
  'zinc' | 'blue' | 'purple' | 'amber'
> = {
  junior: 'zinc',
  mid: 'blue',
  senior: 'purple',
  staff: 'amber',
};

type ViewState = { id: string; editing: boolean } | null;

export function PositionList({ data, interactive }: PositionListProps) {
  const [view, setView] = useState<ViewState>(null);
  const liveQuery = usePositions();
  const detailQuery = usePosition(view?.id);
  const archiveMutation = useArchivePosition();

  const propPositions =
    Array.isArray(data) ? data
    : 'positions' in data ? data.positions
    : 'result' in data ? data.result
    : [];

  const positions =
    interactive && liveQuery.data ? liveQuery.data : propPositions;

  // Detail / edit view
  if (view !== null) {
    if (detailQuery.isPending) {
      return <LoadingState label="Loading position…" />;
    }
    if (detailQuery.data) {
      return (
        <PositionCard
          data={detailQuery.data}
          variant="view"
          initialEditing={view.editing}
          onBack={() => setView(null)}
        />
      );
    }
  }

  // List view
  if (positions.length === 0) {
    return (
      <div className="flex flex-col gap-1">
        <Heading level={4}>Positions</Heading>
        <Text>
          No positions yet. Try: <em>"add a senior backend role at Acme"</em>.
        </Text>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Heading level={4}>Positions ({positions.length})</Heading>
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2 xl:grid-cols-3">
        {positions.map((p) => (
          <div
            key={p.id}
            className="flex items-start gap-3 rounded-md border border-zinc-950/5 p-3 dark:border-white/10"
          >
            {/* ---- main content: clickable for view ---- */}
            {interactive ?
              <button
                type="button"
                onClick={() => setView({ id: p.id, editing: false })}
                className="min-w-0 flex-1 text-left transition-colors hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 cursor-pointer"
              >
                <PositionRowContent p={p} />
              </button>
            : <div className="min-w-0 flex-1">
                <PositionRowContent p={p} />
              </div>
            }

            {/* ---- right column: timestamp + actions ---- */}
            <div className="flex shrink-0 flex-col items-end gap-1.5">
              <Text className="text-xs">
                {formatRelativeTime(p.updated_at)}
              </Text>

              {interactive && !p.archived && (
                <div className="flex items-center gap-1">
                  <Button
                    plain
                    onClick={() => setView({ id: p.id, editing: true })}
                    aria-label={`Edit ${p.title}`}
                    title="Edit this position"
                  >
                    <PencilSquareIcon />
                    Edit
                  </Button>
                  <Button
                    plain
                    onClick={() => archiveMutation.mutate(p.id)}
                    disabled={archiveMutation.isPending}
                    aria-label={`Archive ${p.title}`}
                    title="Archive (soft-delete) this position"
                  >
                    <ArchiveBoxIcon />
                    Archive
                  </Button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- shared row body (used in both button and div variants) ----

function PositionRowContent({ p }: { p: PositionSummaryDTO }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Text className="font-medium text-zinc-900 dark:text-zinc-100">
          {p.title}
        </Text>
        <Badge color={LEVEL_COLOR[p.level]}>{p.level}</Badge>
        {p.archived && <Badge color="zinc">archived</Badge>}
      </div>
      <Text className="text-xs">
        {p.company} · {p.department}
      </Text>
    </>
  );
}
