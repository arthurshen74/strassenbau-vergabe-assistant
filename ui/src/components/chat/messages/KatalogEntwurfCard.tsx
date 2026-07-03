// Renders a catalog write tool's draft envelope (its function_call_output) as a confirm card:
// entity + action, the draft summary / diff (LaTeX for formulas), supersede + close-out warnings,
// and the W11 where-used blast radius. Buttons Aktivieren / Verwerfen drive the human confirm; the
// card re-queries the bundle state (GET /katalog/bundle/{uuid}) so a draft already activated or
// discarded renders truthfully instead of offering dead buttons. The agent proposes; only the human
// commits.

import katex from 'katex';
import 'katex/dist/katex.min.css';

import {
  useBundleAktivieren,
  useBundleVerwerfen,
  useBundleZustand,
} from '../../../api/katalog';
import { Button } from '../../ui/button';
import { Strong, Text } from '../../ui/text';

const ENTITAET_LABEL: Record<string, string> = {
  baustoffe: 'Baustoff',
  maschinen: 'Maschine',
  lieferanten: 'Lieferant',
  preise: 'Preis',
  formeln: 'Formel',
  variablen: 'Variable',
  ausfuehrungsarten: 'Geräteklasse',
  betriebskategorien: 'Betriebskategorie',
  betriebsarten: 'Betriebsart',
  leistung_bauverfahren: 'Leistung → Bauverfahren',
  entwurf: 'Entwurf',
};

const AKTION_LABEL: Record<string, string> = {
  neu: 'Neu',
  aenderung: 'Änderung',
  verwerfen: 'Verwerfen',
};

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function asRecordArray(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v)
    ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
    : [];
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
}

function asString(v: unknown): string | null {
  return typeof v === 'string' ? v : null;
}

function fmt(v: unknown): string {
  if (v == null) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function Latex({ tex }: { tex: string }) {
  const html = katex.renderToString(tex, { displayMode: true, throwOnError: false });
  return (
    <div className="overflow-x-auto py-1" dangerouslySetInnerHTML={{ __html: html }} />
  );
}

function Verwendung({ v }: { v: Record<string, unknown> }) {
  const formeln = asStringArray(v.formeln);
  const vorgaenge = asRecordArray(v.vorgaenge).map((x) => String(x.code));
  const globale = asStringArray(v.globale_variablen);
  if (!formeln.length && !vorgaenge.length && !globale.length) return null;
  return (
    <div className="mt-2 text-xs text-zinc-500">
      <Strong className="text-zinc-600 dark:text-zinc-400">Verwendung: </Strong>
      {[
        formeln.length ? `${formeln.length} Formel(n)` : null,
        vorgaenge.length ? `${vorgaenge.length} Vorgang/Vorgänge` : null,
        globale.length ? `${globale.length} globale` : null,
      ]
        .filter(Boolean)
        .join(' · ')}
    </div>
  );
}

export function KatalogEntwurfCard({ data }: { data: Record<string, unknown> | null }) {
  const bundleUuid = asString(data?.bundle_uuid ?? null);
  const live = useBundleZustand(bundleUuid);
  const aktivieren = useBundleAktivieren();
  const verwerfen = useBundleVerwerfen();
  if (!data) return null;

  const aktion = asString(data.aktion) ?? '';
  const entitaet = asString(data.entitaet) ?? '';
  const schluessel = asString(data.schluessel) ?? '';
  const bericht = asRecord(data.bericht);
  const fehler = asStringArray(bericht?.fehler);
  const aktualisierungen = asStringArray(bericht?.aktualisierungen);
  const diff = asRecordArray(data.diff);
  const entwurf = asRecord(data.entwurf) ?? {};
  const warnungen = asStringArray(data.warnungen);
  const verwendung = asRecord(entwurf.verwendung);

  const zustand = live.data?.zustand;
  const pending = aktivieren.isPending || verwerfen.isPending;
  // Optimistically open until the server state loads; a missing bundle_uuid means nothing was saved.
  const offen = bundleUuid ? (zustand ? zustand === 'offen' : true) : false;

  const titel = `${AKTION_LABEL[aktion] ?? aktion}: ${ENTITAET_LABEL[entitaet] ?? entitaet}`;

  return (
    <div className="rounded-lg border border-zinc-950/10 p-4 dark:border-white/10">
      <div className="flex items-baseline justify-between">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{titel}</div>
        <div className="font-mono text-xs text-zinc-500">{schluessel}</div>
      </div>

      {!bundleUuid && fehler.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-700 dark:text-red-400">
          {fehler.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      ) : null}

      {typeof entwurf.latex === 'string' ? <Latex tex={entwurf.latex} /> : null}
      {typeof entwurf.latex_alt === 'string' ? (
        <div className="text-xs text-zinc-400">
          vorher:
          <Latex tex={entwurf.latex_alt} />
        </div>
      ) : null}

      {diff.length > 0 ? (
        <table className="mt-3 w-full text-sm">
          <thead className="text-zinc-500">
            <tr className="text-left">
              <th className="py-1 pr-2 font-medium">Feld</th>
              <th className="py-1 pr-2 font-medium">alt</th>
              <th className="py-1 font-medium">neu</th>
            </tr>
          </thead>
          <tbody>
            {diff.map((d, i) => (
              <tr key={i} className="border-t border-zinc-950/5 align-top dark:border-white/5">
                <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{fmt(d.feld)}</td>
                <td className="py-1 pr-2 text-zinc-400 line-through">{fmt(d.alt)}</td>
                <td className="py-1 tabular-nums">{fmt(d.neu)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : bundleUuid && !entwurf.latex ? (
        <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
          {Object.entries(entwurf)
            .filter(([k]) => k !== 'verwendung' && k !== 'latex' && k !== 'latex_alt')
            .map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-zinc-500">{k}</dt>
                <dd className="text-zinc-800 tabular-nums dark:text-zinc-200">{fmt(v)}</dd>
              </div>
            ))}
        </dl>
      ) : null}

      {verwendung ? <Verwendung v={verwendung} /> : null}

      {aktualisierungen.length > 0 ? (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-700 dark:text-amber-400">
          {aktualisierungen.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      ) : null}

      {warnungen.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-700 dark:text-amber-400">
          {warnungen.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : null}

      {bundleUuid ? (
        <div className="mt-4 flex items-center gap-2">
          {offen ? (
            <>
              <Button disabled={pending} onClick={() => aktivieren.mutate(bundleUuid)}>
                Aktivieren
              </Button>
              <Button outline disabled={pending} onClick={() => verwerfen.mutate(bundleUuid)}>
                Verwerfen
              </Button>
            </>
          ) : (
            <Text className="text-sm text-zinc-500">
              {zustand === 'aktiviert' ? 'Aktiviert.' : 'Nicht mehr offen.'}
            </Text>
          )}
          {aktivieren.isError || verwerfen.isError ? (
            <span className="text-xs text-red-600 dark:text-red-400">Fehler — bitte erneut versuchen.</span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
