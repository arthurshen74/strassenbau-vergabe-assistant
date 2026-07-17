// Detail panel for one NER flag: sentence/source text, the flag-time entity
// snapshot, the user comment, the full LLM analysis and its provenance, and the
// suggested rule as copyable JSON. Actions: resolve/reopen with a note, override
// the category, re-run analysis, delete.

import { useEffect, useState } from 'react';

import {
  effectiveCategory,
  useDeleteNerFlag,
  useRetryNerFlagAnalysis,
  useUpdateNerFlag,
  type NerFailureCategory,
} from '../../api/nerFlags';
import type { NerFlag } from '../../types/generated';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Select } from '../../components/ui/select';
import { CATEGORY_ORDER, categoryLabel, KIND_LABELS } from '../nlp/nerCategories';

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </span>
      {children}
    </div>
  );
}

export function NerFlagDetail({
  flag,
  onDeleted,
}: {
  flag: NerFlag;
  onDeleted: () => void;
}) {
  const update = useUpdateNerFlag();
  const retry = useRetryNerFlagAnalysis();
  const del = useDeleteNerFlag();

  const [note, setNote] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setNote(flag.resolved_note ?? '');
    setCopied(false);
  }, [flag.ner_flag_uuid, flag.resolved_note]);

  const category = effectiveCategory(flag);
  const isResolved = flag.status === 'resolved';

  const resolve = () =>
    update.mutate({
      uuid: flag.ner_flag_uuid,
      body: { status: 'resolved', resolved_note: note.trim() || null },
    });
  const reopen = () =>
    update.mutate({ uuid: flag.ner_flag_uuid, body: { status: 'open' } });
  const overrideCategory = (value: string) =>
    update.mutate({
      uuid: flag.ner_flag_uuid,
      body: { category_override: (value || null) as NerFailureCategory | null },
    });
  const remove = () => {
    if (window.confirm('Delete this flag?')) {
      del.mutate(flag.ner_flag_uuid, { onSuccess: onDeleted });
    }
  };
  const copyRule = () => {
    if (!flag.suggested_rule) return;
    void navigator.clipboard.writeText(JSON.stringify(flag.suggested_rule, null, 2));
    setCopied(true);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge color="zinc">{KIND_LABELS[flag.kind]}</Badge>
        <Badge color={category === 'ambiguity' ? 'red' : 'blue'}>
          {categoryLabel(category)}
        </Badge>
        <Badge color={isResolved ? 'green' : 'amber'}>{flag.status}</Badge>
      </div>

      <Section label="Span">
        <div className="text-sm">
          <span className="font-mono text-zinc-900 dark:text-zinc-100">
            {flag.span_text}
          </span>{' '}
          <span className="text-zinc-500">
            [{flag.label}
            {flag.expected_label ? ` → ${flag.expected_label}` : ''}]
          </span>
        </div>
      </Section>

      <Section label="Sentence">
        <div className="text-sm text-zinc-700 dark:text-zinc-300">
          {flag.sentence_text}
        </div>
      </Section>

      <Section label="Comment">
        <div className="text-sm text-zinc-700 dark:text-zinc-300">
          {flag.user_comment}
        </div>
      </Section>

      <Section label="Source text">
        <div className="max-h-32 overflow-y-auto rounded-md border border-zinc-200 p-2 text-xs whitespace-pre-wrap text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
          {flag.source_text}
        </div>
      </Section>

      <Section label={`Entity snapshot (${flag.entity_snapshot.length})`}>
        <div className="flex flex-wrap gap-1">
          {flag.entity_snapshot.map((e, i) => (
            <span
              key={`${e.text}-${i}`}
              className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
              title={e.pattern_id ?? 'model guess'}
            >
              {e.label}:{e.text}
            </span>
          ))}
        </div>
      </Section>

      <Section label="LLM analysis">
        {flag.llm_analysis ? (
          <p className="text-sm text-zinc-700 dark:text-zinc-300">{flag.llm_analysis}</p>
        ) : (
          <p className="text-sm text-amber-700 dark:text-amber-400">
            No analysis yet — re-run it below.
          </p>
        )}
      </Section>

      {flag.suggested_rule && (
        <Section label="Suggested rule (advisory)">
          <pre className="overflow-x-auto rounded-md border border-zinc-200 bg-zinc-50 p-2 text-xs dark:border-zinc-700 dark:bg-zinc-900">
            {JSON.stringify(flag.suggested_rule, null, 2)}
          </pre>
          <div className="flex items-center gap-2">
            <Button plain onClick={copyRule}>
              {copied ? 'Copied' : 'Copy JSON'}
            </Button>
            <span className="text-xs text-zinc-500">
              Add it by hand in the Entity Rules page.
            </span>
          </div>
        </Section>
      )}

      {flag.analyzed_at && (
        <Section label="Provenance">
          <div className="text-xs text-zinc-500">
            {flag.llm_model} · prompt v{flag.prompt_version} · {flag.spacy_model_version} ·{' '}
            {new Date(flag.analyzed_at).toLocaleString()}
          </div>
        </Section>
      )}

      <div className="flex flex-col gap-3 rounded-md border border-zinc-200 p-3 dark:border-zinc-700">
        <div className="flex items-center gap-2">
          <span className="w-28 shrink-0 text-xs text-zinc-500">Override category</span>
          <Select
            value={flag.category_override ?? ''}
            onChange={(e) => overrideCategory(e.target.value)}
          >
            <option value="">(use LLM: {categoryLabel(flag.category ?? null)})</option>
            {CATEGORY_ORDER.map((c) => (
              <option key={c} value={c}>
                {categoryLabel(c)}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <Input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Resolve note (e.g. added rule baustoff_bordstein)"
          />
          {isResolved ? (
            <Button outline onClick={reopen} disabled={update.isPending}>
              Reopen
            </Button>
          ) : (
            <Button onClick={resolve} disabled={update.isPending}>
              Resolve
            </Button>
          )}
        </div>

        <div className="flex justify-between">
          <Button
            outline
            onClick={() => retry.mutate(flag.ner_flag_uuid)}
            disabled={retry.isPending}
          >
            {retry.isPending ? 'Analyzing…' : 'Re-analyze'}
          </Button>
          <Button plain onClick={remove} disabled={del.isPending}>
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}
