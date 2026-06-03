// Assistant answer bubble. The Citations panel renders UNDERNEATH the answer, collapsed
// by default. Inline [n] / [n, m] tokens become clickable badges that open the panel and
// scroll to the matching source (data-source-number), briefly highlighting it. A thin
// caret trails the text while the stream is open.

import { useEffect, useRef, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Element } from 'hast';
import { CitationsPanel, type CitationData } from './CitationsPanel';
import { rehypeCitations } from './rehypeCitations';

function CitationBadge({ n, onCite }: { n: number; onCite: (n: number) => void }) {
  return (
    <button
      type="button"
      onClick={() => onCite(n)}
      className="mx-0.5 inline-flex items-center rounded bg-blue-100 px-1 align-super text-[10px] font-semibold text-blue-700 hover:bg-blue-200 dark:bg-blue-900/40 dark:text-blue-300"
    >
      {n}
    </button>
  );
}

interface AssistantMessageProps {
  content: string;
  streaming?: boolean;
  /** Merged retrieval sources for this answer's turn; renders the citations panel. */
  citationData?: CitationData | null;
  projectUuid?: string;
}

export function AssistantMessage({
  content,
  streaming = false,
  citationData,
  projectUuid,
}: AssistantMessageProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [citationsOpen, setCitationsOpen] = useState(false);
  // A new object per citation click (the tick bumps identity) so the effect re-runs even
  // when the panel was already open. Never cleared — the effect only fires on a new click.
  const [scrollRequest, setScrollRequest] = useState<{ n: number; tick: number } | null>(
    null,
  );

  useEffect(() => {
    if (!scrollRequest) return;
    const el = containerRef.current?.querySelector<HTMLElement>(
      `[data-source-number="${scrollRequest.n}"]`,
    );
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('ring-2', 'ring-blue-400');
      window.setTimeout(() => el.classList.remove('ring-2', 'ring-blue-400'), 1500);
    }
  }, [scrollRequest, citationsOpen]);

  const onCite = (n: number) => {
    setCitationsOpen(true);
    setScrollRequest((r) => ({ n, tick: (r?.tick ?? 0) + 1 }));
  };

  return (
    <div className="flex justify-start">
      <div
        ref={containerRef}
        className="max-w-2xl text-sm text-zinc-900 dark:text-zinc-100"
      >
        <div
          className="prose prose-sm dark:prose-invert max-w-none"
          aria-live={streaming ? 'polite' : undefined}
          aria-busy={streaming || undefined}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeCitations]}
            components={
              {
                // `citation` is a custom tag emitted by rehypeCitations; not in Components.
                citation: ({ node }: { node?: Element }) => (
                  <CitationBadge n={Number(node?.properties?.n ?? 0)} onCite={onCite} />
                ),
              } as Components
            }
          >
            {content}
          </ReactMarkdown>
          {streaming && (
            <span
              aria-hidden
              className="ml-0.5 inline-block h-4 w-px translate-y-0.5 animate-pulse bg-zinc-400 dark:bg-zinc-500"
            />
          )}
        </div>
        {citationData && (
          <CitationsPanel
            data={citationData}
            projectUuid={projectUuid}
            open={citationsOpen}
            onToggle={setCitationsOpen}
          />
        )}
      </div>
    </div>
  );
}
