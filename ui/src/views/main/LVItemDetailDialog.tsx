// LV position detail: the position's OZ, Kurztext (with optional STL-Nr), Langtext, optional
// Hinweise, Menge and Einheit. LVItemDetailContent renders the fields and is shared by the dialog
// (opened from a row in the LV Positions table or a chat result) and the inline single-item chat
// card, which caps the Langtext height via constrainLangtext.

import clsx from 'clsx';

import { Dialog, DialogBody, DialogTitle } from '../../components/ui/dialog';
import type { LVItem } from '../../types/generated';

function Field({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
      <div
        className={clsx(
          'text-sm whitespace-pre-wrap text-zinc-900 dark:text-zinc-100',
          valueClassName,
        )}
      >
        {value}
      </div>
    </div>
  );
}

export function LVItemDetailContent({
  item,
  constrainLangtext = false,
}: {
  item: LVItem;
  constrainLangtext?: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Field label="OZ" value={item.oz} />
      <Field
        label={item.stl_nr ? `Kurztext (STL-Nr ${item.stl_nr})` : 'Kurztext'}
        value={item.kurztext}
      />
      <Field
        label="Langtext"
        value={item.langtext}
        valueClassName={constrainLangtext ? 'max-h-[10vh] overflow-y-auto' : undefined}
      />
      {item.hinweis && <Field label="Hinweise" value={item.hinweis} />}
      <div className="grid grid-cols-2 gap-4">
        <Field label="Menge" value={String(item.menge)} />
        <Field label="Einheit" value={item.einheit} />
      </div>
    </div>
  );
}

export function LVItemDetailDialog({
  item,
  open,
  onClose,
}: {
  item: LVItem | null;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} size="2xl">
      <DialogTitle>{item ? `OZ ${item.oz}` : 'LV Position'}</DialogTitle>
      {item && (
        <DialogBody>
          <LVItemDetailContent item={item} />
        </DialogBody>
      )}
    </Dialog>
  );
}
