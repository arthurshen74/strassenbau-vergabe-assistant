// Editor for the versioned project-info RAG queries. Lists the latest version of
// every query key in the chosen language, edits one key at a time and publishes the
// edit as a new version; earlier versions are shown read-only in a collapsible
// history. Keys without a version in the language start from an empty form.

import { useState } from 'react';

import {
  usePublishRagQuery,
  useRagQueries,
  type RagQueryKey,
} from '../../api/ragQueries';
import { ApiError } from '../../api/client';
import type { RagQueryVersionRead } from '../../types/generated';
import { ErrorState } from '../../components/feedback/ErrorState';
import { LoadingState } from '../../components/feedback/LoadingState';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Field, Label } from '../../components/ui/fieldset';
import { Heading } from '../../components/ui/heading';
import { Input } from '../../components/ui/input';
import { Text } from '../../components/ui/text';
import { Textarea } from '../../components/ui/textarea';
import { RagQueryHistory } from './RagQueryHistory';

// UI default only; the server's PROJECT_INFO_LANGUAGE decides what ingestion uses.
const DEFAULT_RAG_QUERY_LANGUAGE = 'de';
const LANGUAGE_RE = /^[a-z]{2}$/;

// Display order; the Record type makes tsc flag a key missing from this list.
const KEY_ORDER: Record<RagQueryKey, number> = {
  'project-name': 0,
  'project-massnahmenummer': 1,
  'project-vergabenummer': 2,
  'project-bauleistung': 3,
  'project-location': 4,
  'project-description': 5,
};
const RAG_QUERY_KEYS = (Object.keys(KEY_ORDER) as RagQueryKey[]).sort(
  (a, b) => KEY_ORDER[a] - KEY_ORDER[b],
);

export function RagQueriesView() {
  const [languageInput, setLanguageInput] = useState(DEFAULT_RAG_QUERY_LANGUAGE);
  const language = languageInput.trim().toLowerCase();
  const valid = LANGUAGE_RE.test(language);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Heading level={4}>RAG Queries (Projektinfo)</Heading>
        <Field className="w-32">
          <Label>Language</Label>
          <Input
            value={languageInput}
            onChange={(e) => setLanguageInput(e.target.value)}
            maxLength={2}
            invalid={!valid}
            placeholder="de"
          />
        </Field>
      </div>
      {valid ? (
        <RagQueryWorkspace key={language} language={language} />
      ) : (
        <Text>Enter a two-letter ISO 639-1 language code (e.g. de, en).</Text>
      )}
    </div>
  );
}

function RagQueryWorkspace({ language }: { language: string }) {
  const query = useRagQueries(language);
  const [selected, setSelected] = useState<RagQueryKey>(RAG_QUERY_KEYS[0]);

  if (query.isPending) return <LoadingState label="Loading RAG queries…" />;
  if (query.isError) {
    return (
      <ErrorState
        message={(query.error as Error).message}
        onRetry={() => query.refetch()}
      />
    );
  }

  const latest = new Map(query.data.map((v) => [v.query_key, v]));
  const current = latest.get(selected) ?? null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <ul className="flex flex-col gap-2">
        {RAG_QUERY_KEYS.map((key) => (
          <li key={key}>
            <KeyCard
              queryKey={key}
              version={latest.get(key) ?? null}
              active={key === selected}
              onSelect={() => setSelected(key)}
            />
          </li>
        ))}
      </ul>
      <div className="flex flex-col gap-4">
        {/* Keyed by version so the form resets to the newly published text. */}
        <RagQueryEditor
          key={`${selected}:${current?.version ?? 0}`}
          queryKey={selected}
          language={language}
          current={current}
        />
        <RagQueryHistory queryKey={selected} language={language} />
      </div>
    </div>
  );
}

function KeyCard({
  queryKey,
  version,
  active,
  onSelect,
}: {
  queryKey: RagQueryKey;
  version: RagQueryVersionRead | null;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={`flex w-full flex-col gap-1 rounded-md border p-3 text-left transition ${
        active
          ? 'border-blue-500 bg-blue-50 dark:border-blue-400 dark:bg-blue-950/30'
          : 'border-zinc-950/5 hover:bg-zinc-50 dark:border-white/10 dark:hover:bg-zinc-800/50'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {version?.name ?? queryKey}
        </span>
        <Badge color={version ? 'zinc' : 'amber'} className="ml-auto">
          {version ? `v${version.version}` : 'not published'}
        </Badge>
      </div>
      <code className="text-xs text-zinc-500 dark:text-zinc-400">{queryKey}</code>
      {version && <Text className="text-xs">{version.description}</Text>}
    </button>
  );
}

function serverDetail(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: unknown } | null;
    if (body && typeof body.detail === 'string') return body.detail;
  }
  return error instanceof Error ? error.message : 'Request failed.';
}

function RagQueryEditor({
  queryKey,
  language,
  current,
}: {
  queryKey: RagQueryKey;
  language: string;
  current: RagQueryVersionRead | null;
}) {
  const [name, setName] = useState(current?.name ?? '');
  const [description, setDescription] = useState(current?.description ?? '');
  const [queryText, setQueryText] = useState(current?.query_text ?? '');
  const [answerInstruction, setAnswerInstruction] = useState(
    current?.answer_instruction ?? '',
  );
  const publish = usePublishRagQuery(queryKey);

  const complete = [name, description, queryText, answerInstruction].every(
    (v) => v.trim() !== '',
  );
  const unchanged =
    current !== null &&
    name === current.name &&
    description === current.description &&
    queryText === current.query_text &&
    answerInstruction === current.answer_instruction;

  const submit = () =>
    publish.mutate({
      language,
      name: name.trim(),
      description: description.trim(),
      query_text: queryText.trim(),
      answer_instruction: answerInstruction.trim(),
    });

  return (
    <div className="flex flex-col gap-3 rounded-md border border-zinc-950/5 p-4 dark:border-white/10">
      <div className="flex flex-wrap items-center gap-2">
        <code className="text-sm text-zinc-700 dark:text-zinc-300">{queryKey}</code>
        <Badge color="zinc">{language}</Badge>
        <span className="ml-auto text-xs text-zinc-500 dark:text-zinc-400">
          {current ? `editing v${current.version}` : 'no version yet'}
        </span>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Field className="flex-1">
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field className="flex-[2]">
          <Label>Description</Label>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
      </div>
      <Field>
        <Label>Query text (retrieval question)</Label>
        <Textarea
          rows={4}
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
        />
      </Field>
      <Field>
        <Label>Answer instruction (synthesis rule)</Label>
        <Textarea
          rows={4}
          value={answerInstruction}
          onChange={(e) => setAnswerInstruction(e.target.value)}
        />
      </Field>
      {publish.isError && (
        <Text className="text-sm text-red-600">{serverDetail(publish.error)}</Text>
      )}
      <div className="flex justify-end">
        <Button onClick={submit} disabled={!complete || unchanged || publish.isPending}>
          {publish.isPending ? 'Publishing…' : 'Publish new version'}
        </Button>
      </div>
    </div>
  );
}
