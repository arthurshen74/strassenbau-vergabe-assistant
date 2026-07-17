// Entities tab: labels ranked by frequency (left), the selected label's
// occurrences (right) — each row showing the matched text, its sentence, and
// either the rule that produced it (pattern id) or a "model guess" badge when no
// rule matched. This is where wrongly-predicted entities become visible.

import { useState } from 'react';

import type { AnalyzeResponse } from '../../types/generated';
import { Badge } from '../../components/ui/badge';

export function EntitiesTab({ analysis }: { analysis: AnalyzeResponse }) {
  const { labels, total_count } = analysis.entities;
  const [selectedLabel, setSelectedLabel] = useState<string | null>(
    labels[0]?.label ?? null,
  );

  const sentencesByHash = new Map(
    analysis.sentences.map((s) => [s.sentence_hash, s.text]),
  );
  const selected = labels.find((l) => l.label === selectedLabel) ?? null;
  const maxCount = Math.max(...labels.map((l) => l.count), 1);

  if (labels.length === 0) {
    return (
      <div className="py-16 text-center text-sm text-zinc-500">
        No entities found in the included blocks.
      </div>
    );
  }

  return (
    <div className="flex gap-4">
      <div className="flex w-56 shrink-0 flex-col gap-1">
        <div className="px-1 text-xs text-zinc-500">
          {total_count.toLocaleString()} entities · {labels.length} labels
        </div>
        {labels.map((stat) => (
          <button
            key={stat.label}
            type="button"
            onClick={() => setSelectedLabel(stat.label)}
            className={`group flex items-center gap-2 rounded px-1 py-0.5 text-left transition hover:bg-zinc-50 dark:hover:bg-zinc-800/50 ${
              selectedLabel === stat.label ? 'bg-zinc-100 dark:bg-zinc-800' : ''
            }`}
            title={`${stat.count} occurrences`}
          >
            <span className="w-28 shrink-0 truncate font-mono text-xs text-zinc-700 dark:text-zinc-300">
              {stat.label}
            </span>
            <span className="relative h-4 flex-1 overflow-hidden rounded-sm bg-zinc-100 dark:bg-zinc-800">
              <span
                className="absolute inset-y-0 left-0 rounded-sm bg-blue-500/80 transition-all group-hover:bg-blue-500"
                style={{ width: `${(stat.count / maxCount) * 100}%` }}
              />
            </span>
            <span className="w-8 shrink-0 text-right text-xs tabular-nums text-zinc-500">
              {stat.count}
            </span>
          </button>
        ))}
      </div>

      <div className="min-w-0 flex-1">
        {selected && (
          <div className="rounded-md border border-zinc-200 p-2 dark:border-zinc-700">
            <div className="mb-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">
              {selected.label}: {selected.count} occurrences
            </div>
            <div className="max-h-[52vh] overflow-y-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-zinc-400">
                    <th className="py-0.5 pr-4 font-normal">Text</th>
                    <th className="py-0.5 pr-4 font-normal">Sentence</th>
                    <th className="py-0.5 font-normal">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {selected.occurrences.map((occ, index) => (
                    <tr
                      key={`${occ.sentence_hash}-${index}`}
                      className="border-t border-zinc-100 dark:border-zinc-800"
                    >
                      <td className="py-0.5 pr-4 font-mono text-zinc-800 dark:text-zinc-200">
                        {occ.text}
                      </td>
                      <td className="max-w-md truncate py-0.5 pr-4 text-zinc-500">
                        {sentencesByHash.get(occ.sentence_hash) ?? ''}
                      </td>
                      <td className="py-0.5">
                        {occ.pattern_id ? (
                          <span className="font-mono text-zinc-500">
                            {occ.pattern_id}
                          </span>
                        ) : (
                          <Badge color="amber">model guess</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
