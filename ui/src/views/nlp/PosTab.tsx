// POS tab: percentage-normalized tag distribution as horizontal bars, with a
// coarse-UD / fine-STTS granularity toggle and click-through to the tokens
// behind a bar.

import { useState } from 'react';

import type { AnalyzeResponse, PosTagStats } from '../../types/generated';

type Granularity = 'ud' | 'stts';

export function PosTab({ analysis }: { analysis: AnalyzeResponse }) {
  const [granularity, setGranularity] = useState<Granularity>('ud');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  const stats: PosTagStats[] = granularity === 'ud' ? analysis.pos.ud : analysis.pos.stts;
  const selected = stats.find((s) => s.tag === selectedTag) ?? null;
  const maxPercentage = Math.max(...stats.map((s) => s.percentage), 1);
  const sentencesByHash = new Map(analysis.sentences.map((s) => [s.sentence_hash, s.text]));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-500">
          {analysis.pos.token_count.toLocaleString()} tokens (whitespace excluded)
        </span>
        <div className="flex rounded-md border border-zinc-200 text-xs dark:border-zinc-700">
          {(['ud', 'stts'] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => {
                setGranularity(g);
                setSelectedTag(null);
              }}
              className={`px-2 py-1 first:rounded-l-md last:rounded-r-md ${
                granularity === g
                  ? 'bg-blue-600 text-white'
                  : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
              }`}
            >
              {g === 'ud' ? 'UD (coarse)' : 'STTS (fine)'}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        {stats.map((stat) => (
          <button
            key={stat.tag}
            type="button"
            onClick={() => setSelectedTag(selectedTag === stat.tag ? null : stat.tag)}
            className={`group flex items-center gap-2 rounded px-1 py-0.5 text-left transition hover:bg-zinc-50 dark:hover:bg-zinc-800/50 ${
              selectedTag === stat.tag ? 'bg-zinc-100 dark:bg-zinc-800' : ''
            }`}
            title={`${stat.count} tokens`}
          >
            <span className="w-16 shrink-0 font-mono text-xs text-zinc-700 dark:text-zinc-300">
              {stat.tag}
            </span>
            <span className="relative h-4 flex-1 overflow-hidden rounded-sm bg-zinc-100 dark:bg-zinc-800">
              <span
                className="absolute inset-y-0 left-0 rounded-sm bg-blue-500/80 transition-all group-hover:bg-blue-500"
                style={{ width: `${(stat.percentage / maxPercentage) * 100}%` }}
              />
            </span>
            <span className="w-14 shrink-0 text-right text-xs tabular-nums text-zinc-500">
              {stat.percentage.toFixed(1)}%
            </span>
          </button>
        ))}
      </div>

      {selected && (
        <div className="rounded-md border border-zinc-200 p-2 dark:border-zinc-700">
          <div className="mb-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">
            {selected.tag}: {selected.count} tokens
          </div>
          <div className="max-h-56 overflow-y-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-zinc-400">
                  <th className="py-0.5 pr-4 font-normal">Token</th>
                  <th className="py-0.5 pr-4 font-normal">Lemma</th>
                  <th className="py-0.5 font-normal">Sentence</th>
                </tr>
              </thead>
              <tbody>
                {selected.tokens.map((token, index) => (
                  <tr
                    key={`${token.sentence_hash}-${index}`}
                    className="border-t border-zinc-100 dark:border-zinc-800"
                  >
                    <td className="py-0.5 pr-4 font-mono text-zinc-800 dark:text-zinc-200">
                      {token.text}
                    </td>
                    <td className="py-0.5 pr-4 font-mono text-zinc-500">{token.lemma}</td>
                    <td className="max-w-md truncate py-0.5 text-zinc-500">
                      {sentencesByHash.get(token.sentence_hash) ?? ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
