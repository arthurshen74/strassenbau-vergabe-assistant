// LV position detail: the position's OZ, Kurztext (with optional STL-Nr), Langtext, optional
// Hinweise, Menge and Einheit. LVItemDetailContent renders the fields and is shared by the dialog
// (opened from a row in the LV Positions table or a chat result) and the inline single-item chat
// card, which caps the Langtext height via constrainLangtext.

import clsx from 'clsx';
import {
  BeakerIcon,
  CalculatorIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from '@heroicons/react/16/solid';

import { Button } from '../../components/ui/button';
import { Dialog, DialogActions, DialogBody, DialogTitle } from '../../components/ui/dialog';
import type { LVItem } from '../../types/generated';
import { nlpPresetForLvItem } from './lvNlpPreset';
import { useNlpModalStore } from '../../store/nlpModal';

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
  showOz = true,
}: {
  item: LVItem;
  constrainLangtext?: boolean;
  showOz?: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      {showOz && <Field label="OZ" value={item.oz} />}
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
  onRunCalculation,
  starting = false,
  onPrev,
  onNext,
}: {
  item: LVItem | null;
  open: boolean;
  onClose: () => void;
  onRunCalculation?: (oz: string) => void;
  starting?: boolean;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  const navigable = onPrev !== undefined || onNext !== undefined;
  const openNlpAnalysis = useNlpModalStore((s) => s.openNlpAnalysis);
  return (
    <Dialog open={open} onClose={onClose} size="2xl">
      <div className="flex items-center justify-between gap-4">
        <DialogTitle className="mb-0">{item ? `OZ ${item.oz}` : 'LV Position'}</DialogTitle>
        {navigable && (
          <div className="flex shrink-0 gap-2">
            <Button outline disabled={!onPrev} onClick={onPrev}>
              <ChevronLeftIcon data-slot="icon" />
              Back
            </Button>
            <Button outline disabled={!onNext} onClick={onNext}>
              Next
              <ChevronRightIcon data-slot="icon" />
            </Button>
          </div>
        )}
      </div>
      {item && (
        <DialogBody className="max-h-[75vh] overflow-y-auto">
          <LVItemDetailContent item={item} showOz={false} />
        </DialogBody>
      )}
      {item && (
        <DialogActions>
          <Button outline onClick={() => openNlpAnalysis(nlpPresetForLvItem(item))}>
            <BeakerIcon data-slot="icon" />
            NLP-Analyse
          </Button>
          {onRunCalculation && (
            <Button color="green" disabled={starting} onClick={() => onRunCalculation(item.oz)}>
              <CalculatorIcon data-slot="icon" />
              {starting ? 'Opening…' : 'Position Chat'}
            </Button>
          )}
        </DialogActions>
      )}
    </Dialog>
  );
}
