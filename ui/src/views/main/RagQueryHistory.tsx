// Read-only list of earlier versions of one RAG query, newest first. Collapsed by
// default; the history is only fetched once it is opened.

import { useState } from 'react';

import { useRagQueryHistory, type RagQueryKey } from '../../api/ragQueries';
import { Badge } from '../../components/ui/badge';
import { Text } from '../../components/ui/text';
import { formatRelativeTime } from '../../lib/format';

export function RagQueryHistory({
  queryKey,
  language,
}: {
  queryKey: RagQueryKey;
  language: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <details
      className="text-sm"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
        Version history
      </summary>
      {open && <HistoryList queryKey={queryKey} language={language} />}
    </details>
  );
}

function HistoryList({
  queryKey,
  language,
}: {
  queryKey: RagQueryKey;
  language: string;
}) {
  const history = useRagQueryHistory(queryKey, language);

  if (history.isPending) return <Text className="mt-2 text-xs">Loading…</Text>;
  if (history.isError) {
    return (
      <Text className="mt-2 text-xs text-red-600">
        {(history.error as Error).message}
      </Text>
    );
  }
  if (history.data.length === 0) {
    return <Text className="mt-2 text-xs">No versions yet.</Text>;
  }

  return (
    <ol className="mt-2 flex flex-col gap-2">
      {history.data.map((v) => (
        <li
          key={v.rag_query_version_uuid}
          className="flex flex-col gap-1 rounded-md border border-zinc-950/5 p-3 text-xs dark:border-white/10"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge color="zinc">v{v.version}</Badge>
            <span className="font-medium text-zinc-800 dark:text-zinc-200">{v.name}</span>
            <span className="ml-auto text-zinc-500 dark:text-zinc-400">
              {formatRelativeTime(v.created_at)}
            </span>
          </div>
          <Text className="text-xs">{v.description}</Text>
          <HistoryField label="Query text" value={v.query_text} />
          <HistoryField label="Answer instruction" value={v.answer_instruction} />
        </li>
      ))}
    </ol>
  );
}

function HistoryField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-medium text-zinc-500 dark:text-zinc-400">{label}</div>
      <pre className="whitespace-pre-wrap rounded bg-zinc-50 p-2 font-sans text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
        {value}
      </pre>
    </div>
  );
}
