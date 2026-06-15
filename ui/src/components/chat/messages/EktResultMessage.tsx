// Renders the calculator's final EKT + VHB 223 Aufgliederung as a result card (the ekt_result
// function_call_output). The form_223 block is present only after the Kalkulator approves the EKT.

import { Strong, Text } from '../../ui/text';

function val(v: unknown): string {
  return v == null ? '—' : String(v);
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : null;
}

export function EktResultMessage({ data }: { data: Record<string, unknown> | null }) {
  if (!data) return null;
  const ekt = asRecord(data.ekt);
  const form = asRecord(data.form_223);
  return (
    <div className="rounded-lg border border-zinc-950/10 p-4 dark:border-white/10">
      <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">EKT result</div>
      {ekt ? (
        <Text className="pt-1">
          Total <Strong>{val(ekt.total_eur)} EUR</Strong> → {val(ekt.per_unit_eur)} EUR/
          {val(ekt.einheit)} (registry v{val(ekt.registry_version)})
        </Text>
      ) : null}
      {form ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 pt-2 text-sm text-zinc-700 dark:text-zinc-300">
          <dt>Zeitansatz</dt>
          <dd>
            {val(form.zeitansatz_h)} h/{val(form.mengeneinheit)}
          </dd>
          <dt>Lohn</dt>
          <dd>{val(form.lohn_eur)} EUR</dd>
          <dt>Stoffe</dt>
          <dd>{val(form.stoffe_eur)} EUR</dd>
          <dt>Geräte</dt>
          <dd>{val(form.geraete_eur)} EUR</dd>
          <dt>Sonstiges</dt>
          <dd>{val(form.sonstiges_eur)} EUR</dd>
        </dl>
      ) : (
        <Text className="pt-2 text-xs">
          Awaiting approval to emit the VHB 223 Aufgliederung.
        </Text>
      )}
    </div>
  );
}
