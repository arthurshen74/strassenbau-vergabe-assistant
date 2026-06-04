// LV Positions tab body: a table of the project's LV items (OZ, Kurztext, Langtext, Menge,
// Einheit). Clicking a row opens the full position in a detail dialog.

import { useState } from 'react';

import { useProjectLvItems } from '../../api/projects';
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

export function LVItemsTable({ projectUuid }: { projectUuid: string }) {
  const lvItems = useProjectLvItems(projectUuid);
  const [selected, setSelected] = useState<LVItem | null>(null);

  if (lvItems.isPending) return <LoadingState label="Loading LV positions…" />;
  if (lvItems.isError) {
    return (
      <ErrorState message={(lvItems.error as Error).message} onRetry={() => lvItems.refetch()} />
    );
  }

  const items = lvItems.data ?? [];
  if (items.length === 0) return <Text>No LV positions yet.</Text>;

  return (
    <>
      <Table dense>
        <TableHead>
          <TableRow>
            <TableHeader>OZ</TableHeader>
            <TableHeader>Kurztext</TableHeader>
            <TableHeader>Langtext</TableHeader>
            <TableHeader className="text-right">Menge</TableHeader>
            <TableHeader>Einheit</TableHeader>
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
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <LVItemDetailDialog
        item={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
