// Stacked-bar rollup of corrections by variable and reason class: which variables
// the model gets wrong, and whether the corrections are model errors at all.

import type { CorrectionSummaryRow } from '../../types/generated';
import { reasonKind, type ReasonKind } from '../../api/variableCorrections';
import { Text } from '../../components/ui/text';

const KIND_COLOR: Record<ReasonKind, string> = {
  model: 'bg-red-500/85',
  gap: 'bg-amber-500/80',
  preference: 'bg-purple-500/70',
  other: 'bg-zinc-400/50',
};

const LEGEND: { kind: ReasonKind; label: string }[] = [
  { kind: 'model', label: 'Modellfehler (falscher_wert · falsche_quelle · einheit)' },
  { kind: 'gap', label: 'Datenlücke (kontext_fehlt)' },
  { kind: 'preference', label: 'Ermessen (kalkulator_ermessen)' },
  { kind: 'other', label: 'Sonstiges' },
];

interface VariableRollup {
  name: string;
  counts: Record<ReasonKind, number>;
  total: number;
}

function rollup(rows: CorrectionSummaryRow[]): VariableRollup[] {
  const byVar = new Map<string, VariableRollup>();
  for (const row of rows) {
    const entry = byVar.get(row.variable_name) ?? {
      name: row.variable_name,
      counts: { model: 0, gap: 0, preference: 0, other: 0 },
      total: 0,
    };
    entry.counts[reasonKind(row.reason)] += row.count;
    entry.total += row.count;
    byVar.set(row.variable_name, entry);
  }
  return [...byVar.values()].sort((a, b) => b.total - a.total);
}

export function CorrectionsAnalysis({ rows }: { rows: CorrectionSummaryRow[] }) {
  const variables = rollup(rows);
  if (variables.length === 0) return null;
  const max = variables[0].total;

  return (
    <div className="rounded-lg border border-zinc-950/10 bg-white p-4 dark:border-white/10 dark:bg-zinc-900">
      <div className="flex flex-wrap items-baseline justify-between gap-2 pb-3">
        <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Korrekturen nach Variable und Grund
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {LEGEND.map((l) => (
            <span
              key={l.kind}
              className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400"
            >
              <span className={`h-2 w-2 rounded-xs ${KIND_COLOR[l.kind]}`} />
              {l.label}
            </span>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {variables.map((v) => (
          <div
            key={v.name}
            className="grid grid-cols-[10rem_1fr_2.5rem] items-center gap-3 sm:grid-cols-[14rem_1fr_2.5rem]"
          >
            <span className="truncate text-right font-mono text-xs">{v.name}</span>
            <div
              className="flex h-4 overflow-hidden rounded-sm bg-zinc-100 dark:bg-zinc-800"
              style={{ width: `${(v.total / max) * 100}%` }}
            >
              {(Object.keys(KIND_COLOR) as ReasonKind[]).map((kind) =>
                v.counts[kind] > 0 ?
                  <div
                    key={kind}
                    className={KIND_COLOR[kind]}
                    style={{ width: `${(v.counts[kind] / v.total) * 100}%` }}
                    title={`${kind}: ${v.counts[kind]}`}
                  />
                : null,
              )}
            </div>
            <span className="text-xs text-zinc-500 tabular-nums">{v.total}</span>
          </div>
        ))}
      </div>

      <Text className="pt-3 text-xs">
        Nur rote Segmente zählen gegen die Extraktionsgenauigkeit.
        kalkulator_ermessen ist ein separates Signal: systematische Abweichung
        von Katalog-Defaults ist ein Hinweis, die Defaults zu rekalibrieren.
      </Text>
    </div>
  );
}
