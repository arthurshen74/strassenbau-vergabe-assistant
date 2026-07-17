// NER Analysis page (MainWindow view): the requirement-3 deliverable. A summary
// header of per-category flag counts (AMBIGUITY red, resolved share shown), a
// filter bar, the flag list, and a detail panel for the selected flag.

import { useState } from 'react';

import {
  effectiveCategory,
  useNerFlags,
  useNerFlagSummary,
  type NerFailureCategory,
  type NerFlagFilters,
  type NerFlagKind,
  type NerFlagStatus,
} from '../../api/nerFlags';
import type { NerFlag, NerCategoryCount } from '../../types/generated';
import { Badge } from '../../components/ui/badge';
import { Select } from '../../components/ui/select';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import {
  CATEGORY_ORDER,
  categoryLabel,
  KIND_LABELS,
} from '../nlp/nerCategories';
import { NerFlagDetail } from './NerFlagDetail';

export function NerAnalysisView() {
  const [filters, setFilters] = useState<NerFlagFilters>({});
  const [selectedUuid, setSelectedUuid] = useState<string | null>(null);

  const summary = useNerFlagSummary();
  const flags = useNerFlags(filters);

  const selected =
    flags.data?.find((f) => f.ner_flag_uuid === selectedUuid) ?? null;

  return (
    <div className="flex flex-col gap-4">
      {summary.isPending ? (
        <LoadingState label="Loading summary…" />
      ) : summary.isError ? (
        <ErrorState message="Failed to load summary." />
      ) : (
        <SummaryHeader
          total={summary.data.total}
          byCategory={summary.data.by_category}
        />
      )}

      <FilterBar filters={filters} onChange={setFilters} />

      <div className="flex min-h-0 gap-4">
        <div className="w-1/2 shrink-0">
          {flags.isPending ? (
            <LoadingState label="Loading flags…" />
          ) : flags.isError ? (
            <ErrorState message="Failed to load flags." />
          ) : flags.data.length === 0 ? (
            <div className="py-8 text-center text-sm text-zinc-500">
              No flags match the filters.
            </div>
          ) : (
            <FlagList
              flags={flags.data}
              selectedUuid={selectedUuid}
              onSelect={setSelectedUuid}
            />
          )}
        </div>

        <div className="min-w-0 flex-1 border-l border-zinc-200 pl-4 dark:border-zinc-700">
          {selected ? (
            <NerFlagDetail flag={selected} onDeleted={() => setSelectedUuid(null)} />
          ) : (
            <div className="py-8 text-center text-sm text-zinc-500">
              Select a flag to see its analysis.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryHeader({
  total,
  byCategory,
}: {
  total: number;
  byCategory: NerCategoryCount[];
}) {
  const counts = new Map(byCategory.map((c) => [c.category, c]));
  const unAnalyzed = counts.get(null);

  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
        {total} flag{total === 1 ? '' : 's'}
      </div>
      <div className="flex flex-wrap gap-2">
        {CATEGORY_ORDER.map((category) => {
          const count = counts.get(category);
          if (!count || count.total === 0) return null;
          return (
            <CategoryTile key={category} category={category} count={count} />
          );
        })}
        {unAnalyzed && unAnalyzed.total > 0 && (
          <CategoryTile category={null} count={unAnalyzed} />
        )}
      </div>
    </div>
  );
}

function CategoryTile({
  category,
  count,
}: {
  category: NerFailureCategory | null;
  count: NerCategoryCount;
}) {
  const isAmbiguity = category === 'ambiguity';
  return (
    <div
      className={`flex min-w-32 flex-col rounded-md border px-3 py-2 ${
        isAmbiguity
          ? 'border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/30'
          : 'border-zinc-200 dark:border-zinc-700'
      }`}
    >
      <span
        className={`text-xs ${
          isAmbiguity ? 'text-red-700 dark:text-red-400' : 'text-zinc-500'
        }`}
      >
        {categoryLabel(category)}
      </span>
      <span
        className={`text-lg font-semibold tabular-nums ${
          isAmbiguity ? 'text-red-700 dark:text-red-300' : 'text-zinc-900 dark:text-zinc-100'
        }`}
      >
        {count.total}
      </span>
      <span className="text-[10px] text-zinc-400">
        {count.resolved_count} resolved
      </span>
    </div>
  );
}

const KINDS: NerFlagKind[] = ['wrong_label', 'not_an_entity', 'missed_entity'];
const STATUSES: NerFlagStatus[] = ['open', 'resolved'];

function FilterBar({
  filters,
  onChange,
}: {
  filters: NerFlagFilters;
  onChange: (filters: NerFlagFilters) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Select
        value={filters.kind ?? ''}
        onChange={(e) =>
          onChange({ ...filters, kind: (e.target.value || undefined) as NerFlagKind | undefined })
        }
      >
        <option value="">All kinds</option>
        {KINDS.map((k) => (
          <option key={k} value={k}>
            {KIND_LABELS[k]}
          </option>
        ))}
      </Select>
      <Select
        value={filters.category ?? ''}
        onChange={(e) =>
          onChange({
            ...filters,
            category: (e.target.value || undefined) as NerFailureCategory | undefined,
          })
        }
      >
        <option value="">All categories</option>
        {CATEGORY_ORDER.map((c) => (
          <option key={c} value={c}>
            {categoryLabel(c)}
          </option>
        ))}
      </Select>
      <Select
        value={filters.status ?? ''}
        onChange={(e) =>
          onChange({
            ...filters,
            status: (e.target.value || undefined) as NerFlagStatus | undefined,
          })
        }
      >
        <option value="">All statuses</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </Select>
    </div>
  );
}

function FlagList({
  flags,
  selectedUuid,
  onSelect,
}: {
  flags: NerFlag[];
  selectedUuid: string | null;
  onSelect: (uuid: string) => void;
}) {
  return (
    <div className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
      {flags.map((flag) => {
        const category = effectiveCategory(flag);
        return (
          <button
            key={flag.ner_flag_uuid}
            type="button"
            onClick={() => onSelect(flag.ner_flag_uuid)}
            className={`flex flex-col gap-1 px-2 py-2 text-left transition hover:bg-zinc-50 dark:hover:bg-zinc-800/50 ${
              selectedUuid === flag.ner_flag_uuid ? 'bg-zinc-100 dark:bg-zinc-800' : ''
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="truncate font-mono text-sm text-zinc-900 dark:text-zinc-100">
                {flag.span_text}
              </span>
              <span className="text-xs text-zinc-400">{flag.label}</span>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
              <Badge color="zinc">{KIND_LABELS[flag.kind]}</Badge>
              <Badge color={category === 'ambiguity' ? 'red' : 'blue'}>
                {categoryLabel(category)}
              </Badge>
              <Badge color={flag.status === 'resolved' ? 'green' : 'amber'}>
                {flag.status}
              </Badge>
              <span className="text-zinc-400">
                {new Date(flag.created_at).toLocaleDateString()}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
