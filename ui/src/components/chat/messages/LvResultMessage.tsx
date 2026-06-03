// Renders a project-chat LV tool result inline: a single Leistungsverzeichnis
// position (view_lvitem) as a card, or a list under a parent OZ (view_lvitems) as
// a compact table.

import type { LVItem } from '../../../types/generated';

function asArray<T>(value: unknown): T[] | null {
  return Array.isArray(value) ? (value as T[]) : null;
}

function asItem(value: unknown): LVItem | null {
  return value && typeof value === 'object' ? (value as LVItem) : null;
}

function ItemCard({ item }: { item: LVItem }) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline gap-2">
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
          {item.oz}
        </span>
        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {item.kurztext}
        </span>
      </div>
      <div className="text-xs text-zinc-500 dark:text-zinc-400">
        {String(item.menge)} {item.einheit}
        {item.stl_nr ? ` · STL ${item.stl_nr}` : ''}
      </div>
      {(item.langtext_resolved || item.langtext) && (
        <p className="whitespace-pre-wrap text-xs text-zinc-700 dark:text-zinc-300">
          {item.langtext_resolved || item.langtext}
        </p>
      )}
    </div>
  );
}

function ItemTable({ items }: { items: LVItem[] }) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-zinc-500 dark:text-zinc-400">
        <tr>
          <th className="py-1 pr-2 font-medium">OZ</th>
          <th className="py-1 pr-2 font-medium">Kurztext</th>
          <th className="py-1 pr-2 text-right font-medium">Menge</th>
          <th className="py-1 font-medium">Einheit</th>
        </tr>
      </thead>
      <tbody className="text-zinc-700 dark:text-zinc-300">
        {items.map((item) => (
          <tr key={item.lv_item_uuid} className="border-t border-zinc-100 dark:border-zinc-800">
            <td className="py-1 pr-2 font-medium whitespace-nowrap">{item.oz}</td>
            <td className="py-1 pr-2">{item.kurztext}</td>
            <td className="py-1 pr-2 text-right whitespace-nowrap">{String(item.menge)}</td>
            <td className="py-1 whitespace-nowrap">{item.einheit}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LvResultMessage({ data }: { data: Record<string, unknown> | null }) {
  const single = asItem(data?.lv_item);
  const list = asArray<LVItem>(data?.lv_items);

  if (!single && (!list || list.length === 0)) {
    return null;
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-2xl rounded-lg border border-zinc-200 bg-white/50 p-3 dark:border-zinc-700 dark:bg-zinc-800/30">
        {single ? <ItemCard item={single} /> : list ? <ItemTable items={list} /> : null}
      </div>
    </div>
  );
}
