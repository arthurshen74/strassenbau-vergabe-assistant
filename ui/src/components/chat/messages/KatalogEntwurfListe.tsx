// Renders the liste_entwuerfe (T33) result as actionable rows: each open draft bundle with its
// entities/keys, authors and live state, plus the same Aktivieren/Verwerfen confirm the
// KatalogEntwurfCard offers — so a draft stays actionable after its original card is gone
// (another conversation, or the conversation was deleted). Rows re-query the bundle state, so a
// stale listing in an old message renders truthfully instead of offering dead buttons.

import {
  useBundleAktivieren,
  useBundleVerwerfen,
  useBundleZustand,
} from '../../../api/katalog';
import { Button } from '../../ui/button';
import { Text } from '../../ui/text';
import { ENTITAET_LABEL, ZUSTAND_LABEL } from './katalogLabels';

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

function EntwurfEintrag({ eintrag }: { eintrag: Record<string, unknown> }) {
  const bundleUuid = asString(eintrag.bundle_uuid);
  const live = useBundleZustand(bundleUuid);
  const aktivieren = useBundleAktivieren();
  const verwerfen = useBundleVerwerfen();
  if (!bundleUuid) return null;

  const entitaeten = asRecordArray(eintrag.entitaeten);
  const benutzer = asStringArray(eintrag.benutzer);
  const zustand = live.data?.zustand;
  const pending = aktivieren.isPending || verwerfen.isPending;
  // Optimistically open until the server state loads; the listing only contains open bundles.
  const offen = zustand ? zustand === 'offen' : true;

  return (
    <div className="rounded-lg border border-zinc-950/10 p-3 dark:border-white/10">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="text-sm text-zinc-800 dark:text-zinc-200">
          {entitaeten.map((e, i) => (
            <span key={i}>
              {i > 0 ? ' · ' : ''}
              <span className="font-medium">
                {ENTITAET_LABEL[String(e.entitaet)] ?? String(e.entitaet)}:{' '}
              </span>
              <span className="font-mono text-xs">{asStringArray(e.schluessel).join(', ')}</span>
            </span>
          ))}
        </div>
        {benutzer.length > 0 ? (
          <span className="text-xs text-zinc-500">{benutzer.join(', ')}</span>
        ) : null}
      </div>
      <div className="mt-2 flex items-center gap-2">
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
            {ZUSTAND_LABEL[zustand ?? ''] ?? 'Nicht mehr offen.'}
          </Text>
        )}
        {aktivieren.isError || verwerfen.isError ? (
          <span className="text-xs text-red-600 dark:text-red-400">
            Fehler — bitte erneut versuchen.
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function KatalogEntwurfListe({ data }: { data: Record<string, unknown> | null }) {
  const eintraege = asRecordArray(data?.eintraege);
  if (!data) return null;
  if (eintraege.length === 0) {
    return <Text className="text-sm text-zinc-500">Keine offenen Entwürfe.</Text>;
  }
  return (
    <div className="flex flex-col gap-2">
      {eintraege.map((e, i) => (
        <EntwurfEintrag key={asString(e.bundle_uuid) ?? String(i)} eintrag={e} />
      ))}
    </div>
  );
}
