// Renders an aggregate_lv_items tool result inline: a collapsed summary line (the per-unit
// subtotal(s) and a "matched N of M positions" coverage note) behind a chevron that expands to
// the itemized breakdown of matched positions and any Bedarfs-/Eventualpositionen flagged
// separately. Each row opens the full position in the LV detail dialog. The total is computed
// server-side in Python; Langtext and the full position detail are resolved from the project's
// LV items.

import { useState } from 'react';
import clsx from 'clsx';
import {
  Disclosure,
  DisclosureButton,
  DisclosurePanel,
} from '@headlessui/react';
import { ChevronRightIcon } from '@heroicons/react/16/solid';

import { useProjectLvItems } from '../../../api/projects';
import { LVItemDetailDialog } from '../../../views/main/LVItemDetailDialog';
import type { AggregateResult, LVItem } from '../../../types/generated';
import { ItemTable } from './ItemTable';

type AggregateTraceStage =
  | 'entry_started'
  | 'items_loaded'
  | 'matched'
  | 'result_ready';

interface AggregateTraceEntry {
  stage: AggregateTraceStage;
  at: string;
  data: Record<string, unknown>;
}

function asResult(value: unknown): AggregateResult | null {
  return value && typeof value === 'object' && 'per_unit' in value ?
      (value as AggregateResult)
    : null;
}

function asTrace(value: unknown): AggregateTraceEntry[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is AggregateTraceEntry => {
    if (!entry || typeof entry !== 'object') return false;
    const maybe = entry as Record<string, unknown>;
    return (
      typeof maybe.stage === 'string' &&
      typeof maybe.at === 'string' &&
      !!maybe.data &&
      typeof maybe.data === 'object' &&
      !Array.isArray(maybe.data)
    );
  });
}

function stageLabel(stage: AggregateTraceStage): string {
  switch (stage) {
    case 'entry_started':
      return 'Entry Started';
    case 'items_loaded':
      return 'Items Loaded';
    case 'matched':
      return 'Matched';
    case 'result_ready':
      return 'Result Ready';
  }
}

function formatIsoDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function DebugTrace({ trace }: { trace: AggregateTraceEntry[] }) {
  return (
    <Disclosure>
      {({ open }) => (
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900/40">
          <DisclosureButton className="flex items-center gap-1 text-xs font-semibold text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
            <ChevronRightIcon
              className={clsx(
                'h-3.5 w-3.5 transition-transform',
                open && 'rotate-90',
              )}
            />
            debug trace ({trace.length})
          </DisclosureButton>
          <DisclosurePanel className="mt-2 space-y-2">
            {trace.map((entry, idx) => (
              <div key={`${entry.stage}-${entry.at}-${idx}`} className="space-y-1">
                <div className="flex flex-wrap items-center gap-x-2 text-xs">
                  <span className="font-medium text-zinc-700 dark:text-zinc-200">
                    {stageLabel(entry.stage)}
                  </span>
                  <span className="text-zinc-500 dark:text-zinc-400">
                    {formatIsoDate(entry.at)}
                  </span>
                </div>
                <pre className="overflow-x-auto rounded bg-white px-2 py-1 text-[11px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                  {JSON.stringify(entry.data, null, 2)}
                </pre>
              </div>
            ))}
          </DisclosurePanel>
        </div>
      )}
    </Disclosure>
  );
}

export function AggregateResultMessage({
  data,
  projectUuid,
}: {
  data: Record<string, unknown> | null;
  projectUuid?: string;
}) {
  const lvItems = useProjectLvItems(projectUuid);
  const [selected, setSelected] = useState<LVItem | null>(null);

  const result = asResult(data);
  if (!result) return null;
  const trace = asTrace(data?.trace);

  const itemsByUuid = new Map<string, LVItem>(
    (lvItems.data ?? []).map((item) => [item.lv_item_uuid, item]),
  );

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-2xl space-y-3 rounded-lg border border-zinc-200 bg-white/50 p-3 dark:border-zinc-700 dark:bg-zinc-800/30">
        <Disclosure>
          {({ open }) => (
            <>
              <DisclosureButton className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 text-left">
                <ChevronRightIcon
                  className={clsx(
                    'h-4 w-4 shrink-0 text-zinc-400 transition-transform',
                    open && 'rotate-90',
                  )}
                />
                {result.per_unit.length > 0 ?
                  result.per_unit.map((s) => (
                    <span
                      key={s.einheit}
                      className="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
                    >
                      {String(s.total)} {s.einheit}
                      <span className="ml-1 text-xs font-normal text-zinc-500 dark:text-zinc-400">
                        ({s.count})
                      </span>
                    </span>
                  ))
                : <span className="text-sm text-zinc-500 dark:text-zinc-400">
                    Keine Summe
                  </span>
                }
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  {result.coverage.matched} von {result.coverage.total}{' '}
                  Positionen
                </span>
              </DisclosureButton>

              <DisclosurePanel className="mt-3 space-y-3">
                {result.breakdown.length > 0 && (
                  <ItemTable
                    items={result.breakdown}
                    itemsByUuid={itemsByUuid}
                    onSelect={setSelected}
                  />
                )}

                {result.bedarfs_eventual.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-xs font-semibold text-amber-700 dark:text-amber-400">
                      Bedarfs-/Eventualpositionen (separat)
                    </div>
                    <ItemTable
                      items={result.bedarfs_eventual}
                      itemsByUuid={itemsByUuid}
                      onSelect={setSelected}
                    />
                  </div>
                )}
              </DisclosurePanel>
            </>
          )}
        </Disclosure>

        {trace.length > 0 && <DebugTrace trace={trace} />}
      </div>

      <LVItemDetailDialog
        item={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
