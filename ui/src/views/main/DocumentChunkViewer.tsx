// Paged chunk table for a document. Toggle SimpleChunks vs LangChain (forms have no LangChain
// chunks, so `simpleOnly` hides the toggle); for SimpleChunks filter by source-doc-type and
// search the text. Each row shows the index, a short preview, and metadata;
// clicking a row opens the full chunk text in a modal. Numbered paging via PageNav.

import { useState } from 'react';

import {
  useDocumentChunks,
  type ChunkFilters,
  type SourceDocType,
} from '../../api/documents';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Select } from '../../components/ui/select';
import { Text } from '../../components/ui/text';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/ui/table';
import { Dialog, DialogBody, DialogTitle } from '../../components/ui/dialog';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { PageNav } from './PageNav';
import type { ChunkRead } from '../../types/generated';

const PAGE_SIZE = 25;

function preview(text: string): string {
  const t = text.trim();
  return t.length > 25 ? `${t.slice(0, 25)}…` : t;
}

function info(c: ChunkRead): string {
  const parts: string[] = [];
  if (c.source_doc_type) parts.push(c.source_doc_type);
  if (c.oz) parts.push(`OZ ${c.oz}`);
  if (c.page != null) parts.push(`page ${c.page}`);
  if (c.pages && c.pages.length > 0) parts.push(`pages ${c.pages.join(', ')}`);
  return parts.join(' · ') || '—';
}

const SOURCE_DOC_TYPES: SourceDocType[] = ['DOCUMENT', 'FORM', 'LV_ITEM', 'LV_TEXT'];

export function DocumentChunkViewer({
  projectUuid,
  documentUuid,
  simpleOnly = false,
}: {
  projectUuid: string;
  documentUuid: string;
  simpleOnly?: boolean;
}) {
  const [source, setSource] = useState<'simple' | 'langchain'>('simple');
  const [docType, setDocType] = useState<'' | SourceDocType>('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<ChunkRead | null>(null);

  const offset = (page - 1) * PAGE_SIZE;
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
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        {!simpleOnly && (
          <label className="flex flex-col gap-1 text-xs text-zinc-500">
            Source
            <Select
              value={source}
              onChange={(e) => {
                setSource(e.target.value as 'simple' | 'langchain');
                setPage(1);
              }}
              className="w-40"
            >
              <option value="simple">SimpleChunks</option>
              <option value="langchain">LangChain</option>
            </Select>
          </label>
        )}
        {source === 'simple' && (
          <label className="flex flex-col gap-1 text-xs text-zinc-500">
            Source type
            <Select
              value={docType}
              onChange={(e) => {
                setDocType(e.target.value as '' | SourceDocType);
                setPage(1);
              }}
              className="w-40"
            >
              <option value="">All</option>
              {SOURCE_DOC_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </label>
        )}
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(search.trim());
            setPage(1);
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
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader className="w-0">Index</TableHeader>
              <TableHeader>Preview</TableHeader>
              <TableHeader>Info</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((c, i) => (
              <TableRow
                key={c.chunk_id}
                className="cursor-pointer"
                onClick={() => setSelected(c)}
              >
                <TableCell>
                  <Badge color="zinc">{c.chunk_index ?? offset + i + 1}</Badge>
                </TableCell>
                <TableCell className="font-mono text-xs">{preview(c.text)}</TableCell>
                <TableCell className="text-xs text-zinc-500">{info(c)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <PageNav page={page} totalPages={totalPages} onChange={setPage} />

      <Dialog open={selected !== null} onClose={() => setSelected(null)} size="3xl">
        <DialogTitle>
          Chunk {selected?.chunk_index ?? ''} {selected ? `· ${info(selected)}` : ''}
        </DialogTitle>
        <DialogBody>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-3 text-sm text-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
            {selected?.text}
          </pre>
        </DialogBody>
      </Dialog>
    </div>
  );
}
