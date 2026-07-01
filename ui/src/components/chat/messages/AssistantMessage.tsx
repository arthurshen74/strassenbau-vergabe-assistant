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
  /**
   * Collapse verbose line-by-line reasoning to its most recent line with an expand toggle
   * (the calculator's streaming reasoning). All lines are kept; only the display collapses.
   */
  collapsible?: boolean;
}

export function AssistantMessage({
  content,
  streaming = false,
  citationData,
  projectUuid,
  collapsible = false,
}: AssistantMessageProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [citationsOpen, setCitationsOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
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

  // Calculator reasoning: collapse the running line-by-line log to its latest line, with a toggle
  // to reveal the full history. A prominent activity row signals the calculation is in progress.
  if (collapsible) {
    const lines = content.split('\n').filter((l) => l.trim() !== '');
    const latest = lines.length > 0 ? lines[lines.length - 1] : '';
    return (
      <div className="flex justify-start">
        <div className="max-w-2xl text-sm text-zinc-900 dark:text-zinc-100">
          <div className="flex items-center gap-2">
            {streaming && (
              <span
                aria-hidden
                className="size-3 shrink-0 animate-spin rounded-full border-2 border-zinc-300 border-t-indigo-500 dark:border-zinc-600 dark:border-t-indigo-400"
              />
            )}
            <span className="font-medium text-indigo-600 dark:text-indigo-400">
              {streaming ? 'Berechnung läuft…' : 'Berechnung'}
            </span>
            {lines.length > 1 && (
              <button
                type="button"
                className="text-xs text-zinc-500 underline hover:text-zinc-700 dark:hover:text-zinc-300"
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded ? 'Verlauf ausblenden' : `Verlauf anzeigen (${lines.length})`}
              </button>
            )}
          </div>
          {expanded ? (
            <pre className="mt-1 whitespace-pre-wrap font-sans text-xs text-zinc-600 dark:text-zinc-400">
              {lines.join('\n')}
            </pre>
          ) : (
            <div className="mt-1 truncate text-xs text-zinc-600 dark:text-zinc-400">{latest}</div>
          )}
        </div>
      </div>
    );
  }

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
