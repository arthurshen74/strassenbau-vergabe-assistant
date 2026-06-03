// The verbose retrieval trace, rendered ABOVE the assistant answer behind a collapsed
// chevron Disclosure (retrieval_debug-style: queries, fused pool, rerank). The retrieved
// sources themselves render below the answer (see CitationsPanel). LANGCHAIN turns carry
// no trace, so this renders nothing for them.

import clsx from 'clsx';
import { Disclosure, DisclosureButton, DisclosurePanel } from '@headlessui/react';
import { ChevronRightIcon } from '@heroicons/react/16/solid';
import type {
  FusedTrace,
  QueryTrace,
  RerankTrace,
  RetrievalContext,
  ScopeTrace,
} from '../../../types/generated';

function asArray<T>(value: unknown): T[] | null {
  return Array.isArray(value) ? (value as T[]) : null;
}

function TraceDetails({
  scope,
  queries,
  fused,
  reranked,
}: {
  scope?: ScopeTrace;
  queries: QueryTrace[];
  fused: FusedTrace[];
  reranked: RerankTrace[];
}) {
  return (
    <Disclosure>
      {({ open }) => (
        <>
          <DisclosureButton className="flex items-center gap-1 text-[11px] font-medium text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
            <ChevronRightIcon
              className={clsx('h-3.5 w-3.5 transition-transform', open && 'rotate-90')}
            />
            Retrieval details
          </DisclosureButton>
          <DisclosurePanel className="mt-2 space-y-2 rounded-md bg-zinc-50 p-2 font-mono text-[11px] text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
            {scope && (
              <div>
                scope: {scope.modality}
                {scope.lv_document_uuid
                  ? ` · lv_doc ${scope.lv_document_uuid.slice(0, 8)}`
                  : ''}
              </div>
            )}
            <div>
              <div className="font-semibold">queries</div>
              {queries.map((q, i) => (
                <div key={i} className="truncate">
                  [{i}] {q.is_original ? '(orig) ' : ''}
                  {q.query_text} — dense {q.dense_hits.length}
                  {q.lexical_hits && q.lexical_hits.length
                    ? ` · bm25 ${q.lexical_hits.length}`
                    : ''}
                </div>
              ))}
            </div>
            {fused.length > 0 && (
              <div>
                <div className="font-semibold">fused pool ({fused.length})</div>
                {fused.slice(0, 12).map((f, i) => (
                  <div key={i} className="truncate">
                    {i + 1}. rrf={f.rrf_score.toFixed(4)}
                    {f.oz ? ` · OZ ${f.oz}` : ''} — {f.text_preview}
                  </div>
                ))}
              </div>
            )}
            {reranked.length > 0 && (
              <div>
                <div className="font-semibold">rerank</div>
                {reranked.map((r, i) => (
                  <div key={i}>
                    {r.rank}. rel={r.relevance_score.toFixed(4)} · {r.chunk_uuid.slice(0, 8)}
                  </div>
                ))}
              </div>
            )}
          </DisclosurePanel>
        </>
      )}
    </Disclosure>
  );
}

export function RetrievalTraceMessage({ data }: { data: Record<string, unknown> | null }) {
  // No trace without a fused pool (e.g. the LANGCHAIN agent emits sources only).
  const queries = asArray<QueryTrace>(data?.queries);
  if (!queries) return null;
  const ctx = data as unknown as RetrievalContext;

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-2xl rounded-lg border border-zinc-200 bg-white/50 p-2 dark:border-zinc-700 dark:bg-zinc-800/30">
        <TraceDetails
          scope={ctx.scope}
          queries={ctx.queries}
          fused={ctx.fused}
          reranked={ctx.reranked ?? []}
        />
      </div>
    </div>
  );
}
