// LV Positions tab body: a searchable table of the project's LV items (OZ, Kurztext, Langtext,
// Menge, Einheit). Submitting a query runs the hybrid BM25/semantic search over the project's
// LV_ITEM chunks and re-orders the table by relevance; clearing it restores the full list.
// Clicking a row opens the full position in a detail dialog.

import { useState } from 'react';
import { CalculatorIcon, MagnifyingGlassIcon } from '@heroicons/react/16/solid';

import { useLvItemSearch, useProjectLvItems } from '../../api/projects';
import { Button } from '../../components/ui/button';
import { Input, InputGroup } from '../../components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/ui/table';
import { Text } from '../../components/ui/text';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import type { LVItem } from '../../types/generated';
import { LVItemDetailDialog } from './LVItemDetailDialog';
import { useRunCalculation } from './useRunCalculation';

export function LVItemsTable({ projectUuid }: { projectUuid: string }) {
  const lvItems = useProjectLvItems(projectUuid);
  const { runCalculation, starting } = useRunCalculation(projectUuid);
  const [selected, setSelected] = useState<LVItem | null>(null);
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const search = useLvItemSearch(projectUuid, query);

  if (lvItems.isPending) return <LoadingState label="Loading LV positions…" />;
  if (lvItems.isError) {
    return (
      <ErrorState message={(lvItems.error as Error).message} onRetry={() => lvItems.refetch()} />
    );
  }

  const allItems = lvItems.data ?? [];
  if (allItems.length === 0) return <Text>No LV positions yet.</Text>;

  const searching = query.length > 0;
  const items = searching ? (search.data ?? []) : allItems;

  // Neighbors of the open item within the currently displayed list, for the dialog's Back/Next.
  const selectedIndex = selected
    ? items.findIndex((i) => i.lv_item_uuid === selected.lv_item_uuid)
    : -1;
  const prevItem = selectedIndex > 0 ? items[selectedIndex - 1] : undefined;
  const nextItem =
    selectedIndex >= 0 && selectedIndex < items.length - 1 ? items[selectedIndex + 1] : undefined;

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setQuery(draft.trim());
  };
  const clearSearch = () => {
    setDraft('');
    setQuery('');
  };

  return (
    <>
      <form onSubmit={submitSearch} className="flex items-center gap-2">
        <div className="flex-1">
          <InputGroup>
            <MagnifyingGlassIcon data-slot="icon" />
            <Input
              type="search"
              name="q"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Search LV positions by keyword, phrase, or OZ…"
              aria-label="Search LV positions"
            />
          </InputGroup>
        </div>
        {searching && (
          <Button type="button" plain onClick={clearSearch}>
            Clear
          </Button>
        )}
      </form>

      {searching && search.isPending ? (
        <LoadingState label="Searching…" />
      ) : searching && search.isError ? (
        <ErrorState message={(search.error as Error).message} onRetry={() => search.refetch()} />
      ) : items.length === 0 ? (
        <Text>No positions match “{query}”.</Text>
      ) : (
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader>OZ</TableHeader>
              <TableHeader>Kurztext</TableHeader>
              <TableHeader>Langtext</TableHeader>
              <TableHeader className="text-right">Menge</TableHeader>
              <TableHeader>Einheit</TableHeader>
              <TableHeader />
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item) => (
              <TableRow
                key={item.lv_item_uuid}
                onClick={() => setSelected(item)}
                className="cursor-pointer hover:bg-zinc-950/2.5 dark:hover:bg-white/2.5"
              >
                <TableCell className="font-medium whitespace-nowrap">{item.oz}</TableCell>
                <TableCell>
                  <div className="max-w-[150px] truncate" title={item.kurztext}>
                    {item.kurztext}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="max-w-[300px] truncate" title={item.langtext}>
                    {item.langtext}
                  </div>
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">{String(item.menge)}</TableCell>
                <TableCell className="whitespace-nowrap">{item.einheit}</TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  <Button
                    color="green"
                    disabled={starting === item.oz}
                    onClick={(e) => {
                      e.stopPropagation();
                      void runCalculation(item.oz);
                    }}
                  >
                    <CalculatorIcon data-slot="icon" />
                    {starting === item.oz ? 'Opening…' : 'Position Chat'}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <LVItemDetailDialog
        item={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
        onRunCalculation={runCalculation}
        starting={selected !== null && starting === selected.oz}
        onPrev={prevItem ? () => setSelected(prevItem) : undefined}
        onNext={nextItem ? () => setSelected(nextItem) : undefined}
      />
    </>
  );
}
