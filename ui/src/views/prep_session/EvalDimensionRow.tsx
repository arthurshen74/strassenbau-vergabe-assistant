// One dimension row in the eval drawer: name on the left, dot scale on the right.
// For normal rows, long rationale text is clamped to one line with a "(more…)"
// toggle to expand it. For the "overall" (hire_signal) row the rationale is
// always fully rendered.

import { useState } from 'react';
import { DotScale } from '../../components/ui/DotScale';
import type { EvalDimension, EvalScoreDTO } from '../../types/generated';

interface EvalDimensionRowProps {
  dimension: EvalDimension;
  /** Override the display label (e.g. "Overall" for hire_signal). */
  displayName?: string;
  score: EvalScoreDTO | undefined;
  scaleMax: number;
  /** "overall" rows always show the full rationale; "normal" rows truncate with a toggle. */
  variant?: 'normal' | 'overall';
}

export function EvalDimensionRow({
  dimension,
  displayName,
  score,
  scaleMax,
  variant = 'normal',
}: EvalDimensionRowProps) {
  const [expanded, setExpanded] = useState(false);
  const isOverall = variant === 'overall';

  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium capitalize text-zinc-800 dark:text-zinc-100">
          {displayName ?? dimension.name}
        </p>

        {score?.rationale && (
          <div className="mt-0.5">
            {isOverall ? (
              // Overall: always fully rendered
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {score.rationale}
              </p>
            ) : expanded ? (
              // Normal expanded
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {score.rationale}{' '}
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  className="whitespace-nowrap font-medium text-zinc-400 underline-offset-2 hover:underline dark:text-zinc-500"
                >
                  less
                </button>
              </p>
            ) : (
              // Normal collapsed — single line clamp with "more…" link
              <p className="flex items-baseline gap-1 text-xs text-zinc-500 dark:text-zinc-400">
                <span className="line-clamp-1 min-w-0">{score.rationale}</span>
                <button
                  type="button"
                  onClick={() => setExpanded(true)}
                  className="shrink-0 whitespace-nowrap font-medium text-zinc-400 underline-offset-2 hover:underline dark:text-zinc-500"
                >
                  more…
                </button>
              </p>
            )}
          </div>
        )}
      </div>

      <div className="shrink-0 pt-0.5">
        <DotScale
          score={score?.score ?? null}
          scaleMax={scaleMax}
          label={displayName ?? dimension.name}
        />
      </div>
    </div>
  );
}
