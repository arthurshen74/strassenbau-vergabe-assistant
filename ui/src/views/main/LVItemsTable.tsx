// LV Positions tab body: a table of the project's LV items (OZ, Kurztext, Langtext, Menge,
// Einheit). Clicking a row opens the full position in a detail dialog.

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { createCalculation } from '../../api/calculations';
import { conversationKeys } from '../../api/conversations';
import { useProjectLvItems } from '../../api/projects';
import { useMainWindowStore } from '../../store/mainWindow';
import { Button } from '../../components/ui/button';
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
import type { ConversationRead, LVItem } from '../../types/generated';
import { LVItemDetailDialog } from './LVItemDetailDialog';

export function LVItemsTable({ projectUuid }: { projectUuid: string }) {
  const lvItems = useProjectLvItems(projectUuid);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const closeMainWindow = useMainWindowStore((s) => s.closeMainWindow);
  const [selected, setSelected] = useState<LVItem | null>(null);
  const [starting, setStarting] = useState<string | null>(null);

  // Create the ekt_calculator conversation, seed the list cache so it resolves immediately, close
  // the (global) main window overlay so the conversation underneath is visible, then redirect to it;
  // the conversation view auto-opens the run stream for a fresh run.
  const runCalculation = async (oz: string) => {
    setStarting(oz);
    try {
      const convo = await createCalculation(projectUuid, oz);
      qc.setQueryData<ConversationRead[]>(conversationKeys.list(), (old) =>
        old ? [convo, ...old] : [convo],
      );
      qc.invalidateQueries({ queryKey: conversationKeys.all });
      closeMainWindow();
      navigate(`/c/${convo.conversation_uuid}`);
    } finally {
      setStarting(null);
    }
  };

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
                  outline
                  disabled={starting === item.oz}
                  onClick={(e) => {
                    e.stopPropagation();
                    void runCalculation(item.oz);
                  }}
                >
                  {starting === item.oz ? 'Starting…' : 'Run calculation'}
                </Button>
              </TableCell>
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
