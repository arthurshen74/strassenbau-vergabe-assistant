// Eval curation view for one project (/p/:projectUuid/eval): stat tiles over the
// gold sets and corrections, then the three curation tabs (Kalkulation-Gold,
// RAG-Fragen, Korrekturen).

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import clsx from 'clsx';
import { useProject, useProjectLvItems } from '../../api/projects';
import { useGroundTruthList } from '../../api/groundTruth';
import {
  MODEL_ERROR_REASONS,
  useCorrectionsSummary,
} from '../../api/variableCorrections';
import { Heading } from '../../components/ui/heading';
import { Text } from '../../components/ui/text';
import { ErrorState } from '../../components/feedback/ErrorState';
import { useRagGroundTruthList } from '../../api/ragGroundTruth';
import { GoldTab } from './GoldTab';
import { RagTab } from './RagTab';
import { CorrectionsTab } from './CorrectionsTab';
import { RunsTab } from './RunsTab';

const ART_EINGABE = 'eingabe';

type EvalTab = 'gold' | 'rag' | 'korrekturen' | 'laeufe';

function StatTile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'warn' | 'err';
}) {
  return (
    <div className="rounded-lg border border-zinc-950/10 bg-white px-4 py-3 dark:border-white/10 dark:bg-zinc-900">
      <div className="text-xs font-medium tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
        {label}
      </div>
      <div
        className={
          tone === 'warn' ? 'text-xl font-semibold text-amber-600 dark:text-amber-400'
          : tone === 'err' ?
            'text-xl font-semibold text-red-600 dark:text-red-400'
          : 'text-xl font-semibold text-zinc-900 dark:text-zinc-100'
        }
      >
        {value}
      </div>
      {hint && (
        <div className="text-xs text-zinc-400 dark:text-zinc-500">{hint}</div>
      )}
    </div>
  );
}

export function EvalView() {
  const { projectUuid } = useParams<{ projectUuid: string }>();
  const project = useProject(projectUuid);
  const lvItems = useProjectLvItems(projectUuid);
  const gold = useGroundTruthList(projectUuid);
  const summary = useCorrectionsSummary(projectUuid);
  const ragQuestions = useRagGroundTruthList(projectUuid);
  const [tab, setTab] = useState<EvalTab>('gold');

  if (!projectUuid) {
    return <ErrorState message="Missing project id" />;
  }

  const goldRows = gold.data ?? [];
  const staleCount = goldRows.filter((g) => g.stale).length;
  const variables = goldRows.flatMap((g) => Object.values(g.gold_variables));
  const eingabeCount = variables.filter((v) => v.art === ART_EINGABE).length;
  const correctionCount = (summary.data ?? []).reduce((n, r) => n + r.count, 0);
  const modelErrorCount = (summary.data ?? [])
    .filter((r) => r.reason != null && MODEL_ERROR_REASONS.includes(r.reason))
    .reduce((n, r) => n + r.count, 0);
  const ragRows = ragQuestions.data ?? [];
  const ragWithoutRefs = ragRows.filter((r) => r.refs_missing).length;

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex h-12 shrink-0 items-center border-b border-zinc-950/5 px-4 dark:border-white/5">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          Evaluation — {project.data?.project_name ?? '…'}
        </div>
      </header>

      <div className="flex flex-col gap-5 p-6">
        <div>
          <Heading level={4}>Ground Truth &amp; Korrekturen</Heading>
          <Text className="text-sm">
            Gold-Daten kuratieren und Experten-Korrekturen aus dem EKT-Flow
            analysieren.
          </Text>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatTile
            label="Gold-Positionen"
            value={String(goldRows.length)}
            hint={
              lvItems.data ? `von ${lvItems.data.length} LV-Positionen` : undefined
            }
          />
          <StatTile
            label="Gold-Variablen"
            value={String(variables.length)}
            hint={`davon ${eingabeCount} EINGABE`}
          />
          <StatTile
            label="Veraltet"
            value={String(staleCount)}
            hint="Rezept/Katalog geändert"
            tone={staleCount > 0 ? 'warn' : undefined}
          />
          <StatTile label="Korrekturen" value={String(correctionCount)} />
          <StatTile
            label="Modellfehler-Anteil"
            value={
              correctionCount > 0 ?
                `${Math.round((modelErrorCount / correctionCount) * 100)} %`
              : '—'
            }
            hint={
              correctionCount > 0 ?
                `${modelErrorCount} von ${correctionCount} Korrekturen`
              : 'noch keine Korrekturen'
            }
            tone={modelErrorCount > 0 ? 'err' : undefined}
          />
          <StatTile
            label="RAG-Fragen"
            value={String(ragRows.length)}
            hint={
              ragWithoutRefs > 0 ? `${ragWithoutRefs} ohne Referenzen` : undefined
            }
            tone={ragWithoutRefs > 0 ? 'warn' : undefined}
          />
        </div>

        <div className="border-b border-zinc-950/10 dark:border-white/10">
          <nav aria-label="Tabs" className="-mb-px flex space-x-8">
            {(
              [
                { id: 'gold', label: `Kalkulation-Gold (${goldRows.length})` },
                { id: 'rag', label: `RAG-Fragen (${ragRows.length})` },
                { id: 'korrekturen', label: `Korrekturen (${correctionCount})` },
                { id: 'laeufe', label: 'Läufe' },
              ] as { id: EvalTab; label: string }[]
            ).map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  'border-b-2 px-1 pb-2 text-sm font-medium',
                  tab === t.id ?
                    'border-blue-500 text-zinc-900 dark:text-zinc-100'
                  : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200',
                )}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>

        {tab === 'gold' ?
          <GoldTab projectUuid={projectUuid} />
        : tab === 'rag' ?
          <RagTab projectUuid={projectUuid} />
        : tab === 'korrekturen' ?
          <CorrectionsTab projectUuid={projectUuid} />
        : <RunsTab projectUuid={projectUuid} />}
      </div>
    </div>
  );
}
