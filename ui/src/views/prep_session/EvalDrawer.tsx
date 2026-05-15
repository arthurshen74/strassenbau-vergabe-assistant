// Right-side overlay drawer showing live evaluation scores.
// Mirrors the PromptLogDrawer pattern: Headless.Dialog + slide-in panel
// at w-[420px], mounted inside PrepSessionView (not at AppShell level —
// it's per-session and unmounts with the view).
//
// Data flow:
//   - Dimensions come as props (inlined on PrepSessionConversationDTO,
//     no second fetch needed).
//   - Scores come from the useEvalScores TanStack Query cache, which is
//     kept current by the eval-stream subscription in usePrepSessionConversation.
//   - Opening the drawer shows the latest cached scores immediately —
//     no spinner, because the subscription runs whether the drawer is open or not.

import { useEffect, useState } from 'react';
import * as Headless from '@headlessui/react';
import { ChartBarIcon, XMarkIcon } from '@heroicons/react/20/solid';
import { useEvalScores } from '../../api/sessions';
import { EvalDimensionRow } from './EvalDimensionRow';
import { formatRelativeTime } from '../../lib/format';
import type { EvalDimension } from '../../types/generated';

interface EvalDrawerProps {
  open: boolean;
  onClose: () => void;
  sessionId: string;
  dimensions: EvalDimension[];
  scaleMax: number;
}

export function EvalDrawer({
  open,
  onClose,
  sessionId,
  dimensions,
  scaleMax,
}: EvalDrawerProps) {
  const { data: scores } = useEvalScores(sessionId);

  // Tick "updated N ago" every 15s while the drawer is open.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!open) return;
    const id = setInterval(() => setTick((t) => t + 1), 15_000);
    return () => clearInterval(id);
  }, [open]);

  // Latest score timestamp across all dimensions.
  const latestCreatedAt = scores
    ? Object.values(scores).reduce<string | null>((latest, s) => {
        if (!latest) return s.created_at;
        return s.created_at > latest ? s.created_at : latest;
      }, null)
    : null;

  // Separate hire_signal from other dimensions so it always renders last.
  const mainDimensions = dimensions.filter((d) => d.name !== 'hire_signal');
  const hireSignal = dimensions.find((d) => d.name === 'hire_signal');

  return (
    <Headless.Dialog open={open} onClose={onClose} className="relative z-40">
      {/* Backdrop */}
      <Headless.DialogBackdrop className="fixed inset-0 bg-zinc-950/20 transition duration-200 data-closed:opacity-0" />

      {/* Slide-in panel from the right */}
      <div className="fixed inset-0 flex justify-end">
        <Headless.DialogPanel className="flex h-full w-[420px] flex-col bg-white shadow-2xl ring-1 ring-zinc-950/5 transition duration-200 data-closed:translate-x-full dark:bg-zinc-900 dark:ring-white/10">

          {/* Header */}
          <div className="flex shrink-0 items-center gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-700">
            <ChartBarIcon className="h-5 w-5 text-zinc-400" />
            <Headless.DialogTitle className="flex-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Live evaluation
            </Headless.DialogTitle>
            {latestCreatedAt && (
              <span className="text-xs text-zinc-400 dark:text-zinc-500">
                updated {formatRelativeTime(latestCreatedAt)}
              </span>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Dimension list */}
          <div className="flex-1 overflow-y-auto px-4 py-2">
            {dimensions.length === 0 ? (
              <p className="py-8 text-center text-sm text-zinc-400">
                No evaluation dimensions configured.
              </p>
            ) : (
              <>
                <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {mainDimensions.map((dim) => (
                    <EvalDimensionRow
                      key={dim.name}
                      dimension={dim}
                      score={scores?.[dim.name]}
                      scaleMax={scaleMax}
                    />
                  ))}
                </div>

                {hireSignal && (
                  <>
                    <div className="my-3 border-t border-zinc-200 dark:border-zinc-700" />
                    <EvalDimensionRow
                      dimension={hireSignal}
                      displayName="Overall"
                      score={scores?.[hireSignal.name]}
                      scaleMax={scaleMax}
                      variant="overall"
                    />
                  </>
                )}
              </>
            )}
          </div>
        </Headless.DialogPanel>
      </div>
    </Headless.Dialog>
  );
}
