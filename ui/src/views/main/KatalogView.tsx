// Katalog workspace view (REZEPT_REDESIGN_PLAN §5): browse the persisted catalog's definitions and
// their SCD-2 Versionshistorie. Sidebar-opened + REST-fetched (mirrors ExecutionLogView). Three
// tabs — Globale Variablen, Variablen (filterable by Gruppe), Basisformeln — each a list → detail
// with the entity's prose/parameters/cascade and its version ledger. Read-only for now; editing
// rides the existing bundle write path (pruefen → aktivieren) and is added on top.

import { useState } from 'react';
import {
  useKatalogAktive,
  useKatalogVersionen,
  type KatalogEntitaet,
} from '../../api/katalog';
import type { KatalogZeile } from '../../types/generated';
import { Heading } from '../../components/ui/heading';
import { Text } from '../../components/ui/text';
import { Badge } from '../../components/ui/badge';
import { Select } from '../../components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/ui/table';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { formatTimestamp } from '../../lib/format';

const TABS: { entitaet: KatalogEntitaet; label: string }[] = [
  { entitaet: 'globale_variablen', label: 'Globale Variablen' },
  { entitaet: 'variablen', label: 'Variablen' },
  { entitaet: 'formeln', label: 'Basisformeln' },
];

type Payload = Record<string, unknown>;

function str(p: Payload, key: string): string | null {
  const v = p[key];
  return v == null ? null : String(v);
}

function arr(p: Payload, key: string): Payload[] {
  const v = p[key];
  return Array.isArray(v) ? (v as Payload[]) : [];
}

// A short secondary label for a list row (the human-readable name).
function rowLabel(z: KatalogZeile): string | null {
  return str(z.payload, 'bezeichnung') ?? str(z.payload, 'beschreibung') ?? str(z.payload, 'ausdruck');
}

const STATUS_COLOR: Record<KatalogZeile['status'], 'zinc' | 'green' | 'amber' | 'rose'> = {
  entwurf: 'amber',
  aktiv: 'green',
  archiviert: 'zinc',
  verworfen: 'rose',
};

export function KatalogView() {
  const [entitaet, setEntitaet] = useState<KatalogEntitaet>('formeln');
  const [gruppe, setGruppe] = useState<string>('alle');
  const [selected, setSelected] = useState<string | null>(null);

  const query = useKatalogAktive(entitaet);

  function pickTab(e: KatalogEntitaet) {
    setEntitaet(e);
    setSelected(null);
  }

  const rows = (query.data ?? []).filter(
    (z) => entitaet !== 'variablen' || gruppe === 'alle' || str(z.payload, 'gruppe') === gruppe,
  );
  const active = rows.find((z) => z.schluessel === selected) ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {TABS.map(({ entitaet: e, label }) => (
          <button
            key={e}
            type="button"
            onClick={() => pickTab(e)}
            className={
              'rounded-md px-3 py-1.5 text-sm transition ' +
              (e === entitaet
                ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
                : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800')
            }
          >
            {label}
          </button>
        ))}
        {entitaet === 'variablen' && (
          <Select
            value={gruppe}
            onChange={(e) => setGruppe(e.target.value)}
            className="ml-2 max-w-[12rem]"
          >
            <option value="alle">Alle Gruppen</option>
            <option value="stammdaten">Stammdaten</option>
            <option value="kontext">Kontext</option>
          </Select>
        )}
        <div className="ml-auto text-xs text-zinc-500 dark:text-zinc-400">
          {rows.length} aktive Einträge
        </div>
      </div>

      {query.isPending ? (
        <LoadingState label="Katalog laden…" />
      ) : query.isError ? (
        <ErrorState message="Katalog konnte nicht geladen werden." />
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
          <div className="min-h-0 overflow-y-auto rounded-lg border border-zinc-950/5 dark:border-white/10">
            {rows.map((z) => (
              <button
                key={z.schluessel}
                type="button"
                onClick={() => setSelected(z.schluessel)}
                className={
                  'block w-full border-b border-zinc-950/5 px-3 py-2 text-left last:border-0 dark:border-white/5 ' +
                  (z.schluessel === selected
                    ? 'bg-blue-50 dark:bg-blue-950/40'
                    : 'hover:bg-zinc-50 dark:hover:bg-zinc-900')
                }
              >
                <div className="font-mono text-sm text-zinc-900 dark:text-zinc-100">
                  {z.schluessel}
                </div>
                {rowLabel(z) && (
                  <div className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                    {rowLabel(z)}
                  </div>
                )}
              </button>
            ))}
            {rows.length === 0 && (
              <div className="p-3 text-sm text-zinc-500 dark:text-zinc-400">Keine Einträge.</div>
            )}
          </div>

          <div className="min-h-0 overflow-y-auto">
            {active ? (
              <Detail entitaet={entitaet} zeile={active} />
            ) : (
              <Text>Einen Eintrag wählen, um Definition und Versionshistorie zu sehen.</Text>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Detail({ entitaet, zeile }: { entitaet: KatalogEntitaet; zeile: KatalogZeile }) {
  const p = zeile.payload;
  const felder: { label: string; wert: string | null }[] = [
    { label: 'Bezeichnung', wert: str(p, 'bezeichnung') },
    { label: 'Gruppe', wert: str(p, 'gruppe') },
    { label: 'Einheit', wert: str(p, 'einheit') },
    { label: 'Ausdruck', wert: str(p, 'ausdruck') },
    { label: 'Datentyp', wert: str(p, 'datentyp') },
    { label: 'Zielvariable', wert: str(p, 'ziel_variable') },
    { label: 'Erforderlich', wert: str(p, 'erforderlich') },
    { label: 'Standort', wert: str(p, 'ist_standort') },
  ].filter((f) => f.wert != null);

  const parameter = arr(p, 'parameter');
  const aufloesung = arr(p, 'aufloesung');

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Heading level={3} className="font-mono">
          {zeile.schluessel}
        </Heading>
        {str(p, 'beschreibung') && (
          <Text className="mt-1 whitespace-pre-wrap">{str(p, 'beschreibung')}</Text>
        )}
        {str(p, 'rag_prompt') && (
          <Text className="mt-1 whitespace-pre-wrap italic">{str(p, 'rag_prompt')}</Text>
        )}
      </div>

      {felder.length > 0 && (
        <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-sm">
          {felder.map((f) => (
            <div key={f.label} className="contents">
              <dt className="text-zinc-500 dark:text-zinc-400">{f.label}</dt>
              <dd className="text-zinc-900 dark:text-zinc-100">{f.wert}</dd>
            </div>
          ))}
        </dl>
      )}

      {parameter.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Parameter
          </div>
          <Table dense>
            <TableHead>
              <TableRow>
                <TableHeader>Name</TableHeader>
                <TableHeader>Einheit</TableHeader>
                <TableHeader>Beschreibung</TableHeader>
                <TableHeader>Standard</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {parameter.map((pp, i) => (
                <TableRow key={i}>
                  <TableCell className="font-mono">{str(pp, 'name')}</TableCell>
                  <TableCell>{str(pp, 'einheit') ?? '—'}</TableCell>
                  <TableCell>{str(pp, 'beschreibung')}</TableCell>
                  <TableCell>{str(pp, 'standard') ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {aufloesung.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Auflösungs-Kaskade
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {aufloesung.map((s, i) => (
              <Badge key={i} color="zinc">
                {str(s, 'methode')}
                {str(s, 'konstante') != null ? ` = ${str(s, 'konstante')}` : ''}
                {str(s, 'stammdaten_pfad') != null ? ` (${str(s, 'stammdaten_pfad')})` : ''}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <Versionshistorie entitaet={entitaet} schluessel={zeile.schluessel} />
    </div>
  );
}

function Versionshistorie({
  entitaet,
  schluessel,
}: {
  entitaet: KatalogEntitaet;
  schluessel: string;
}) {
  const query = useKatalogVersionen(entitaet, schluessel);
  const versionen = query.data ?? [];

  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Versionshistorie
      </div>
      {query.isPending ? (
        <LoadingState label="Historie…" />
      ) : (
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader>Version</TableHeader>
              <TableHeader>Status</TableHeader>
              <TableHeader>gültig ab</TableHeader>
              <TableHeader>gültig bis</TableHeader>
              <TableHeader>Benutzer</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {versionen.map((z) => (
              <TableRow key={z.zeile_uuid}>
                <TableCell>{z.version}</TableCell>
                <TableCell>
                  <Badge color={STATUS_COLOR[z.status]}>{z.status}</Badge>
                </TableCell>
                <TableCell>{formatTimestamp(z.gueltig_ab)}</TableCell>
                <TableCell>{z.gueltig_bis ? formatTimestamp(z.gueltig_bis) : '—'}</TableCell>
                <TableCell>{z.benutzer ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
