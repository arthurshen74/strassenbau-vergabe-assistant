// Collapsible citations panel rendered UNDERNEATH the assistant answer. Hidden by
// default; the chevron toggles it, and clicking an inline [n] citation in the answer
// opens it and scrolls to the matching source. Each source shows the page thumbnail it
// came from (click to enlarge) and expands to the full chunk text.
//
// Sources are ContextChunk[], numbered to match the answer's [n] citations. MessageList merges
// a turn's retrieval results (across get_project_context / get_lv_context calls) into the
// CitationData passed in.

import { useState } from 'react';
import clsx from 'clsx';
import { ChevronRightIcon } from '@heroicons/react/16/solid';
import { apiBase } from '../../../api/client';
import type { ContextChunk, ThumbnailRef } from '../../../types/generated';

export interface CitationData {
  context: ContextChunk[];
}

function thumbnailUrl(projectUuid: string, thumbnail: ThumbnailRef): string {
  return `${apiBase}/projects/${projectUuid}/documents/${thumbnail.document_uuid}/pages/${thumbnail.page_number}/thumbnail`;
}

function PageThumbnail({ url, onZoom }: { url: string; onZoom: () => void }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="flex h-20 w-16 shrink-0 items-center justify-center rounded border border-dashed border-zinc-300 text-[10px] text-zinc-400 dark:border-zinc-700">
        no preview
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={onZoom}
      className="shrink-0"
      title="Enlarge page"
    >
      <img
        src={url}
        loading="lazy"
        onError={() => setFailed(true)}
        className="h-20 w-16 rounded border border-zinc-200 object-cover object-top hover:ring-2 hover:ring-blue-400 dark:border-zinc-700"
        alt="Source page"
      />
    </button>
  );
}

function SourceNumber({ n }: { n: number }) {
  return (
    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-blue-100 text-xs font-semibold text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
      {n}
    </span>
  );
}

function sourceHeader(chunk: ContextChunk): string {
  const parts: string[] = [chunk.source_doc_type];
  if (chunk.oz) parts.push(`OZ ${chunk.oz}`);
  if (chunk.stl_nr) parts.push(`STL ${chunk.stl_nr}`);
  if (chunk.source_doc_pages.length)
    parts.push(`p. ${chunk.source_doc_pages.join(', ')}`);
  return parts.join(' · ');
}

function ContextSourceRow({
  chunk,
  projectUuid,
  onZoom,
}: {
  chunk: ContextChunk;
  projectUuid?: string;
  onZoom: (url: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const url =
    projectUuid && chunk.thumbnail ?
      thumbnailUrl(projectUuid, chunk.thumbnail)
    : null;
  return (
    <div
      data-source-number={chunk.source_number}
      className="flex gap-3 rounded-md border border-zinc-200 p-2 dark:border-zinc-700"
    >
      <SourceNumber n={chunk.source_number} />
      {url && (
        <PageThumbnail
          url={url}
          onZoom={() => onZoom(url)}
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
          {sourceHeader(chunk)}
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className={clsx(
            'mt-0.5 block w-full text-left text-xs text-zinc-700 dark:text-zinc-300',
            !expanded && 'line-clamp-2',
          )}
        >
          {chunk.chunk_text}
        </button>
      </div>
    </div>
  );
}

export function CitationsPanel({
  data,
  projectUuid,
  open,
  onToggle,
}: {
  data: CitationData;
  projectUuid?: string;
  open: boolean;
  onToggle: (open: boolean) => void;
}) {
  const [zoom, setZoom] = useState<string | null>(null);
  const count = data.context.length;
  if (count === 0) return null;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => onToggle(!open)}
        className="flex items-center gap-1 text-[11px] font-medium text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
      >
        <ChevronRightIcon
          className={clsx(
            'h-3.5 w-3.5 transition-transform',
            open && 'rotate-90',
          )}
        />
        {count} {count === 1 ? 'Quelle' : 'Quellen'}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {data.context.map((c) => (
            <ContextSourceRow
              key={c.source_number}
              chunk={c}
              projectUuid={projectUuid}
              onZoom={setZoom}
            />
          ))}
        </div>
      )}
      {zoom && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-8"
          onClick={() => setZoom(null)}
        >
          <img
            src={zoom}
            className="max-h-[65vh] rounded border border-zinc-950/10 dark:border-white/10"
            alt="Source page"
          />
        </div>
      )}
    </div>
  );
}
