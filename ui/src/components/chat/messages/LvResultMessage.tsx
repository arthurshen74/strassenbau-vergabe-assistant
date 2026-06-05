// Renders a project-chat LV tool result inline: a single Leistungsverzeichnis position
// (view_lvitem) as a detail card with a height-capped Langtext, or a list under a parent OZ
// (view_lvitems) as the shared compact table. The list shows five rows at a time and pages in
// another five ("more") or expands fully ("show all"); each row opens the full position in the LV
// detail dialog.

import { useState } from 'react';

import {
  LVItemDetailContent,
  LVItemDetailDialog,
} from '../../../views/main/LVItemDetailDialog';
import type { LVItem } from '../../../types/generated';
import { ItemTable } from './ItemTable';

const PAGE_SIZE = 5;

function asArray<T>(value: unknown): T[] | null {
  return Array.isArray(value) ? (value as T[]) : null;
}

function asItem(value: unknown): LVItem | null {
  return value && typeof value === 'object' ? (value as LVItem) : null;
}

function LvItemList({
  items,
  onSelect,
}: {
  items: LVItem[];
  onSelect: (item: LVItem) => void;
}) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const visible = items.slice(0, visibleCount);
  const hasMore = visibleCount < items.length;
  const itemsByUuid = new Map<string, LVItem>(
    items.map((item) => [item.lv_item_uuid, item]),
  );

  return (
    <>
      <div className="text-xs text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 italic">
        There are {items.length} item(s)
      </div>
      <ItemTable
        items={visible}
        itemsByUuid={itemsByUuid}
        onSelect={onSelect}
      />
      {hasMore && (
        <div className="mt-2 text-xs text-zinc-400 dark:text-zinc-500">
          <button
            type="button"
            onClick={() =>
              setVisibleCount((n) => Math.min(n + PAGE_SIZE, items.length))
            }
            className="font-medium text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            more
          </button>
          <span className="px-1.5">|</span>
          <button
            type="button"
            onClick={() => setVisibleCount(items.length)}
            className="font-medium text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            show all
          </button>
        </div>
      )}
    </>
  );
}

export function LvResultMessage({
  data,
}: {
  data: Record<string, unknown> | null;
}) {
  const [selected, setSelected] = useState<LVItem | null>(null);

  const single = asItem(data?.lv_item);
  const list = asArray<LVItem>(data?.lv_items);

  if (!single && (!list || list.length === 0)) {
    return null;
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-2xl rounded-lg border border-zinc-200 bg-white/50 p-3 dark:border-zinc-700 dark:bg-zinc-800/30">
        {single ?
          <LVItemDetailContent
            item={single}
            constrainLangtext
          />
        : list ?
          <LvItemList
            items={list}
            onSelect={setSelected}
          />
        : null}
      </div>

      <LVItemDetailDialog
        item={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
