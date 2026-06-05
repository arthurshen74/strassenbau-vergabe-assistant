// Compact table of LV positions shared by the LV and aggregate chat results: OZ, a Langtext
// preview (resolved from the full position when available, otherwise the line's Kurztext), Menge
// and Einheit. Rows whose full position is resolvable are clickable and open the LV detail dialog
// via onSelect.

import clsx from 'clsx';

import type { AggregateLineItem, LVItem } from '../../../types/generated';

const LANGTEXT_PREVIEW_CHARS = 47;

function langtextPreview(item: LVItem | undefined, fallback: string): string {
  const text = item?.langtext_resolved || item?.langtext || fallback;
  return text.length > LANGTEXT_PREVIEW_CHARS ?
      `${text.slice(0, LANGTEXT_PREVIEW_CHARS)}...`
    : text;
}

export function ItemTable({
  items,
  itemsByUuid,
  onSelect,
}: {
  items: AggregateLineItem[];
  itemsByUuid: Map<string, LVItem>;
  onSelect: (item: LVItem) => void;
}) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-zinc-500 dark:text-zinc-400">
        <tr>
          <th className="py-1 pr-2 font-medium">OZ</th>
          <th className="py-1 pr-2 font-medium">Langtext</th>
          <th className="py-1 pr-2 text-right font-medium">Menge</th>
          <th className="py-1 font-medium">Einheit</th>
        </tr>
      </thead>
      <tbody className="text-zinc-700 dark:text-zinc-300">
        {items.map((item) => {
          const full = itemsByUuid.get(item.lv_item_uuid);
          return (
            <tr
              key={item.lv_item_uuid}
              onClick={full ? () => onSelect(full) : undefined}
              className={clsx(
                'border-t border-zinc-100 dark:border-zinc-800',
                full &&
                  'cursor-pointer hover:bg-zinc-950/2.5 dark:hover:bg-white/2.5',
              )}
            >
              <td className="py-1 pr-2 font-medium whitespace-nowrap">
                {item.oz}
              </td>
              <td className="py-1 pr-2">
                {langtextPreview(full, item.kurztext)}
              </td>
              <td className="py-1 pr-2 text-right whitespace-nowrap">
                {String(item.menge)}
              </td>
              <td className="py-1 whitespace-nowrap">{item.einheit}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
