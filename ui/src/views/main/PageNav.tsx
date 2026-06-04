// Centered numbered pagination (Previous / 1 … n / Next) with a top-border active marker.
// Shared by the document-detail tabs. 1-based page; onChange fires with the target page.

import { ArrowLongLeftIcon, ArrowLongRightIcon } from '@heroicons/react/20/solid';

const ITEM = 'inline-flex items-center border-t-2 px-4 pt-4 text-sm font-medium';
const INACTIVE =
  'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 ' +
  'dark:text-zinc-400 dark:hover:border-white/20 dark:hover:text-zinc-200';
const ACTIVE = 'border-indigo-500 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400';
const DISABLED = 'cursor-not-allowed border-transparent text-zinc-300 dark:text-zinc-600';

function pageItems(current: number, total: number): Array<number | 'gap'> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out: Array<number | 'gap'> = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) out.push('gap');
  for (let p = start; p <= end; p += 1) out.push(p);
  if (end < total - 1) out.push('gap');
  out.push(total);
  return out;
}

export function PageNav({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <nav className="flex items-center justify-between border-t border-zinc-950/10 dark:border-white/10">
      <div className="-mt-px flex w-0 flex-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          className={`${ITEM} pr-1 ${page <= 1 ? DISABLED : INACTIVE}`}
        >
          <ArrowLongLeftIcon
            aria-hidden="true"
            className="mr-3 size-5 text-zinc-400 dark:text-zinc-500"
          />
          Previous
        </button>
      </div>
      <div className="hidden md:-mt-px md:flex">
        {pageItems(page, totalPages).map((it, i) =>
          it === 'gap' ? (
            <span key={`gap-${i}`} className={`${ITEM} border-transparent text-zinc-500`}>
              …
            </span>
          ) : (
            <button
              key={it}
              type="button"
              aria-current={it === page ? 'page' : undefined}
              onClick={() => onChange(it)}
              className={`${ITEM} ${it === page ? ACTIVE : INACTIVE}`}
            >
              {it}
            </button>
          ),
        )}
      </div>
      <div className="-mt-px flex w-0 flex-1 justify-end">
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
          className={`${ITEM} pl-1 ${page >= totalPages ? DISABLED : INACTIVE}`}
        >
          Next
          <ArrowLongRightIcon
            aria-hidden="true"
            className="ml-3 size-5 text-zinc-400 dark:text-zinc-500"
          />
        </button>
      </div>
    </nav>
  );
}
