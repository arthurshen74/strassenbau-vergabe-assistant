// Renders the calculator's final result card (the ekt_result function_call_output): the EKT row
// (Einheitspreis/Gesamtpreis + Kostenlinien), the long-form narration, the Nachweistabelle (the
// derivation tree from ctx.werte, every variable with provenance), and any warnings.

import { useState } from 'react';

import { Strong, Text } from '../../ui/text';

const QUELLE_LABEL: Record<string, string> = {
  langtext: 'Langtext',
  rag: 'RAG',
  hitl: 'Chat/HITL',
  konstante: 'Standardwert',
  stammdaten: 'Stammdaten',
  formel: 'Formel',
};

function val(v: unknown): string {
  return v == null ? '—' : String(v);
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : null;
}

function asRecordArray(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v)
    ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
    : [];
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
}

export function EktResultMessage({ data }: { data: Record<string, unknown> | null }) {
  const [showNachweis, setShowNachweis] = useState(false);
  if (!data) return null;
  const ekt = asRecord(data.ekt_zeile);
  const nachweis = asRecordArray(data.nachweis_tabelle);
  const warnungen = asStringArray(data.warnungen);
  const beschreibung = typeof data.beschreibung === 'string' ? data.beschreibung : '';

  return (
    <div className="rounded-lg border border-zinc-950/10 p-4 dark:border-white/10">
      <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">EKT-Ergebnis</div>

      {ekt ? (
        <>
          <Text className="pt-1">
            {val(ekt.leistung)} <span className="text-zinc-500">· {val(ekt.bauverfahren)}</span>
          </Text>
          <Text className="pt-1">
            <Strong>
              {val(ekt.ep_eur)} EUR/{val(ekt.einheit)}
            </Strong>{' '}
            (EP) · {val(ekt.gp_eur)} EUR (GP, {val(ekt.menge)} {val(ekt.einheit)})
          </Text>

          <table className="mt-3 w-full text-sm">
            <tbody>
              {asRecordArray(ekt.kostenlinien).map((k, i) => (
                <tr key={i} className="border-t border-zinc-950/5 dark:border-white/5">
                  <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{val(k.kostenart)}</td>
                  <td className="py-1 pr-2 text-zinc-500">{val(k.variable)}</td>
                  <td className="py-1 text-right tabular-nums">{val(k.betrag_eur)} EUR</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {beschreibung ? <Text className="pt-3">{beschreibung}</Text> : null}

      {warnungen.length > 0 ? (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-700 dark:text-amber-400">
          {warnungen.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : null}

      {nachweis.length > 0 ? (
        <div className="pt-3">
          <button
            type="button"
            className="text-xs font-medium text-zinc-600 underline dark:text-zinc-400"
            onClick={() => setShowNachweis((s) => !s)}
          >
            {showNachweis ? 'Nachweistabelle ausblenden' : `Nachweistabelle anzeigen (${nachweis.length})`}
          </button>
          {showNachweis ? (
            <table className="mt-2 w-full text-xs">
              <thead className="text-zinc-500">
                <tr className="text-left">
                  <th className="py-1 pr-2 font-medium">Variable</th>
                  <th className="py-1 pr-2 text-right font-medium">Wert</th>
                  <th className="py-1 pr-2 font-medium">Quelle</th>
                  <th className="py-1 font-medium">Beleg / Formel</th>
                </tr>
              </thead>
              <tbody>
                {nachweis.map((n, i) => (
                  <tr key={i} className="border-t border-zinc-950/5 align-top dark:border-white/5">
                    <td className="py-1 pr-2">
                      <div className="text-zinc-800 dark:text-zinc-200">{val(n.bezeichnung) || val(n.name)}</div>
                      <div className="text-zinc-400">{val(n.name)}</div>
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums whitespace-nowrap">
                      {val(n.wert)} {n.einheit ? String(n.einheit) : ''}
                    </td>
                    <td className="py-1 pr-2 whitespace-nowrap">
                      {QUELLE_LABEL[val(n.quelle)] ?? val(n.quelle)}
                    </td>
                    <td className="py-1 text-zinc-500">
                      {n.ausdruck ? <code className="text-[11px]">{String(n.ausdruck)}</code> : val(n.beleg) || ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
