// Paged chunk viewer for a document. Toggle SimpleChunks vs LangChain chunks; for SimpleChunks,
// filter by source-doc-type and search the text. First / Back / Next / Last / GoToIndex paging.

import { useState } from 'react';

import { useDocumentChunks, type ChunkFilters } from '../../api/documents';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Select } from '../../components/ui/select';
import { Text } from '../../components/ui/text';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';

const PAGE_SIZE = 25;

export function DocumentChunkViewer({
  projectUuid,
  documentUuid,
}: {
  projectUuid: string;
  documentUuid: string;
}) {
  const [source, setSource] = useState<'simple' | 'langchain'>('simple');
  const [docType, setDocType] = useState<'' | 'DOCUMENT' | 'LV_ITEM'>('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);

  const filters: ChunkFilters = {
    source,
    doc_type: source === 'simple' && docType ? docType : undefined,
    q: query || undefined,
    offset,
    limit: PAGE_SIZE,
  };
  const result = useDocumentChunks(projectUuid, documentUuid, filters);
  const items = result.data?.items ?? [];
  const total = result.data?.total ?? 0;

  const reset = () => setOffset(0);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-zinc-500">
          Source
          <Select
            value={source}
            onChange={(e) => {
              setSource(e.target.value as 'simple' | 'langchain');
              reset();
            }}
            className="w-40"
          >
            <option value="simple">SimpleChunks</option>
            <option value="langchain">LangChain</option>
          </Select>
        </label>
        {source === 'simple' && (
          <label className="flex flex-col gap-1 text-xs text-zinc-500">
            Source type
            <Select
              value={docType}
              onChange={(e) => {
                setDocType(e.target.value as '' | 'DOCUMENT' | 'LV_ITEM');
                reset();
              }}
              className="w-40"
            >
              <option value="">All</option>
              <option value="DOCUMENT">DOCUMENT</option>
              <option value="LV_ITEM">LV_ITEM</option>
            </Select>
          </label>
        )}
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(search.trim());
            reset();
          }}
        >
          <label className="flex flex-col gap-1 text-xs text-zinc-500">
            Search text
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="contains…"
              className="w-56"
            />
          </label>
          <Button type="submit" plain>
            Search
          </Button>
        </form>
      </div>

      {result.isPending ? (
        <LoadingState label="Loading chunks…" />
      ) : result.isError ? (
        <ErrorState message={(result.error as Error).message} onRetry={() => result.refetch()} />
      ) : items.length === 0 ? (
        <Text>No chunks.</Text>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((c, i) => (
            <li
              key={c.chunk_id}
              className="rounded border border-zinc-950/10 p-2 dark:border-white/10"
            >
              <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
                <Badge color="zinc">
                  #{c.chunk_index ?? offset + i}
                </Badge>
                {c.source_doc_type && <span>{c.source_doc_type}</span>}
                {c.oz && <span>OZ {c.oz}</span>}
                {c.page != null && <span>page {c.page}</span>}
                {c.pages && c.pages.length > 0 && <span>pages {c.pages.join(', ')}</span>}
              </div>
              <div className="whitespace-pre-wrap text-sm text-zinc-800 dark:text-zinc-200">
                {c.text}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center justify-end gap-2">
        <Button plain disabled={offset === 0} onClick={() => setOffset(0)}>
          First
        </Button>
        <Button plain disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Back
        </Button>
        <Text className="text-xs">
          {total === 0 ? '0' : `${offset + 1}–${offset + items.length}`} of {total}
        </Text>
        <Button
          plain
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Next
        </Button>
        <Button
          plain
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => setOffset(Math.max(0, (Math.ceil(total / PAGE_SIZE) - 1) * PAGE_SIZE))}
        >
          Last
        </Button>
        <Input
          type="number"
          min={1}
          max={total}
          aria-label="Go to index"
          placeholder="index"
          className="w-24"
          onChange={(e) => {
            const n = Number(e.target.value);
            if (Number.isFinite(n) && n >= 1 && n <= total) setOffset(n - 1);
          }}
        />
      </div>
    </div>
  );
}
