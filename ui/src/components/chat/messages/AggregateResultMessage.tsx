// Renders an aggregate_lv_items tool result inline: the per-unit subtotal(s), the itemized
// breakdown of matched positions, any Bedarfs-/Eventualpositionen flagged separately, and a
// "matched N of M positions" coverage note. The total is computed server-side in Python.

import type {
  AggregateLineItem,
  AggregateResult,
} from '../../../types/generated';

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

function ItemTable({ items }: { items: AggregateLineItem[] }) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-zinc-500 dark:text-zinc-400">
        <tr>
          <th className="py-1 pr-2 font-medium">OZ</th>
          <th className="py-1 pr-2 font-medium">Kurztext</th>
          <th className="py-1 pr-2 text-right font-medium">Menge</th>
          <th className="py-1 font-medium">Einheit</th>
        </tr>
      </thead>
      <tbody className="text-zinc-700 dark:text-zinc-300">
        {items.map((item) => (
          <tr
            key={item.lv_item_uuid}
            className="border-t border-zinc-100 dark:border-zinc-800"
          >
            <td className="py-1 pr-2 font-medium whitespace-nowrap">
              {item.oz}
            </td>
            <td className="py-1 pr-2">{item.kurztext}</td>
            <td className="py-1 pr-2 text-right whitespace-nowrap">
              {String(item.menge)}
            </td>
            <td className="py-1 whitespace-nowrap">{item.einheit}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AggregateResultMessage({
  data,
}: {
  data: Record<string, unknown> | null;
}) {
  const result = asResult(data);
  if (!result) return null;
  const trace = asTrace(data?.trace);

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-2xl space-y-3 rounded-lg border border-zinc-200 bg-white/50 p-3 dark:border-zinc-700 dark:bg-zinc-800/30">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
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
            {result.coverage.matched} von {result.coverage.total} Positionen
          </span>
        </div>

        {result.breakdown.length > 0 && <ItemTable items={result.breakdown} />}

        {result.bedarfs_eventual.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-amber-700 dark:text-amber-400">
              Bedarfs-/Eventualpositionen (separat)
            </div>
            <ItemTable items={result.bedarfs_eventual} />
          </div>
        )}

        {trace.length > 0 && (
          <details className="rounded-md border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900/40">
            <summary className="cursor-pointer list-none text-xs font-semibold uppercase tracking-wide text-zinc-500 marker:hidden dark:text-zinc-400">
              Trace ({trace.length})
            </summary>
            <div className="mt-2 space-y-2">
              {trace.map((entry, idx) => (
                <div
                  key={`${entry.stage}-${entry.at}-${idx}`}
                  className="space-y-1"
                >
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
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
