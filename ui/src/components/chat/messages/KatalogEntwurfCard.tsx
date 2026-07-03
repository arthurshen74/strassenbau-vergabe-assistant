// Renders a catalog write tool's draft envelope (its function_call_output) as a confirm card:
// entity + action, the draft summary / diff (LaTeX for formulas), supersede + close-out warnings,
// and the W11 where-used blast radius. A rezept_entwurf_speichern envelope renders sectioned
// instead: Leistung, Vorgang-Kette, Formeln (LaTeX), Variablen, Wiederverwendung/Neu panels.
// Buttons Aktivieren / Verwerfen drive the human confirm; the card re-queries the bundle state
// (GET /katalog/bundle/{uuid}) so a draft already activated or discarded renders truthfully
// instead of offering dead buttons. The agent proposes; only the human commits.

import katex from 'katex';
import 'katex/dist/katex.min.css';
import type { ReactNode } from 'react';

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
  bundle: 'Katalog-Bundle',
};

const AKTION_LABEL: Record<string, string> = {
  neu: 'Neu',
  aenderung: 'Änderung',
  verwerfen: 'Verwerfen',
  rezept: 'Rezept',
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

function Sektion({ titel, children }: { titel: string; children: ReactNode }) {
  return (
    <div className="mt-3">
      <div className="text-xs font-medium text-zinc-500">{titel}</div>
      <div className="flex flex-col gap-0.5 pt-1">{children}</div>
    </div>
  );
}

// The sectioned recipe view of a rezept_entwurf_speichern envelope: the bundle's entities plus
// the justification panels (the reuse-vs-mint story the human judges).
function RezeptEntwurf({
  entwurf,
  wiederverwendung,
  neu,
}: {
  entwurf: Record<string, unknown>;
  wiederverwendung: Record<string, unknown>[];
  neu: Record<string, unknown>[];
}) {
  const leistungen = asRecordArray(entwurf.leistungen);
  const bauverfahren = asRecordArray(entwurf.bauverfahren);
  const vorgaenge = asRecordArray(entwurf.vorgaenge);
  const formeln = asRecordArray(entwurf.formeln);
  const variablen = asRecordArray(entwurf.variablen);
  const baustoffe = asRecordArray(entwurf.baustoffe);
  const maschinen = asRecordArray(entwurf.maschinen);
  const lieferanten = asRecordArray(entwurf.lieferanten);
  const preise = asRecordArray(entwurf.preise);
  const mapping = asRecord(entwurf.leistung_bauverfahren) ?? {};

  return (
    <>
      {leistungen.length > 0 ? (
        <Sektion titel="Leistung">
          {leistungen.map((l, i) => (
            <Text key={i} className="text-sm">
              <Strong>{fmt(l.code)}</Strong> — {fmt(l.name)}{' '}
              <span className="text-zinc-500">({fmt(l.einheit)})</span>
            </Text>
          ))}
        </Sektion>
      ) : null}

      {bauverfahren.length > 0 || vorgaenge.length > 0 ? (
        <Sektion titel="Vorgang-Kette">
          {bauverfahren.map((b, i) => (
            <Text key={i} className="text-sm">
              <Strong>{fmt(b.code)}</Strong> — {fmt(b.name)}{' '}
              <span className="font-mono text-xs text-zinc-500">
                [{asStringArray(b.vorgang_codes).join(' → ')}]
              </span>
            </Text>
          ))}
          {vorgaenge.map((v, i) => {
            const kosten = asRecord(v.kostenvariablen) ?? {};
            return (
              <Text key={`v${i}`} className="text-sm">
                <Strong>{fmt(v.code)}</Strong> — {fmt(v.name)}
                <span className="text-xs text-zinc-500">
                  {v.ausfuehrungsart_code ? ` · ${fmt(v.ausfuehrungsart_code)}` : ''}
                  {v.betriebsart_code ? ` · ${fmt(v.betriebsart_code)}` : ''}
                  {Object.entries(kosten)
                    .map(([ka, name]) => ` · ${ka}: ${fmt(name)}`)
                    .join('')}
                </span>
              </Text>
            );
          })}
        </Sektion>
      ) : null}

      {formeln.length > 0 ? (
        <Sektion titel="Formeln">
          {formeln.map((f, i) => (
            <div key={i}>
              <Text className="font-mono text-xs text-zinc-500">
                {fmt(f.name)}
                {f.einheit ? ` [${fmt(f.einheit)}]` : ''}
              </Text>
              {typeof f.latex === 'string' ? (
                <Latex tex={f.latex} />
              ) : (
                <Text className="font-mono text-xs">{fmt(f.ausdruck)}</Text>
              )}
            </div>
          ))}
        </Sektion>
      ) : null}

      {variablen.length > 0 ? (
        <Sektion titel="Variablen">
          {variablen.map((v, i) => (
            <Text key={i} className="text-sm">
              <span className="text-xs text-zinc-500">{fmt(v.gruppe)} · </span>
              <Strong>{fmt(v.name)}</Strong> — {fmt(v.bezeichnung)}
              <span className="text-xs text-zinc-500">
                {v.wert != null ? ` · ${fmt(v.wert)}${v.einheit ? ` ${fmt(v.einheit)}` : ''}` : ''}
                {` · ${asStringArray(v.kaskade).join(' → ')}`}
              </span>
            </Text>
          ))}
        </Sektion>
      ) : null}

      {baustoffe.length > 0 || maschinen.length > 0 || lieferanten.length > 0 || preise.length > 0 ? (
        <Sektion titel="Stammdaten">
          {baustoffe.map((b, i) => (
            <Text key={`b${i}`} className="text-sm">
              Baustoff <Strong>{fmt(b.code)}</Strong> — {fmt(b.name)}
            </Text>
          ))}
          {maschinen.map((m, i) => (
            <Text key={`m${i}`} className="text-sm">
              Maschine <Strong>{fmt(m.code)}</Strong> — {fmt(m.hersteller)} {fmt(m.modell)}
            </Text>
          ))}
          {lieferanten.map((l, i) => (
            <Text key={`l${i}`} className="text-sm">
              Lieferant <Strong>{fmt(l.code)}</Strong> — {fmt(l.name)}
            </Text>
          ))}
          {preise.map((p, i) => (
            <Text key={`p${i}`} className="text-sm">
              Preis {fmt(p.lieferant_code)}/{fmt(p.baustoff_code)} — {fmt(p.preis_eur_pro_t)} €/t
            </Text>
          ))}
        </Sektion>
      ) : null}

      {Object.keys(mapping).length > 0 ? (
        <Sektion titel="Leistung → Bauverfahren">
          {Object.entries(mapping).map(([lk, bvs]) => (
            <Text key={lk} className="text-sm">
              <Strong>{lk}</Strong> → {asStringArray(bvs).join(', ')}
            </Text>
          ))}
        </Sektion>
      ) : null}

      {wiederverwendung.length > 0 ? (
        <Sektion titel={`Wiederverwendung (${wiederverwendung.length})`}>
          {wiederverwendung.map((e, i) => (
            <Text key={i} className="text-xs">
              <Strong className="font-mono">{fmt(e.code)}</Strong>
              <span className="text-zinc-500"> — {fmt(e.warum)}</span>
            </Text>
          ))}
        </Sektion>
      ) : null}

      {neu.length > 0 ? (
        <Sektion titel={`Neu geprägt (${neu.length})`}>
          {neu.map((e, i) => (
            <Text key={i} className="text-xs">
              <Strong className="font-mono">{fmt(e.code)}</Strong>
              <span className="text-zinc-500"> — {fmt(e.warum_nicht_vorhanden)}</span>
            </Text>
          ))}
        </Sektion>
      ) : null}
    </>
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
  const istRezept = aktion === 'rezept';

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

      {istRezept ? (
        <RezeptEntwurf
          entwurf={entwurf}
          wiederverwendung={asRecordArray(data.wiederverwendung)}
          neu={asRecordArray(data.neu)}
        />
      ) : null}

      {!istRezept && typeof entwurf.latex === 'string' ? <Latex tex={entwurf.latex} /> : null}
      {!istRezept && typeof entwurf.latex_alt === 'string' ? (
        <div className="text-xs text-zinc-400">
          vorher:
          <Latex tex={entwurf.latex_alt} />
        </div>
      ) : null}

      {istRezept ? null : diff.length > 0 ? (
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
