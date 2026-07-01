// Renders the control for a paused EKT calculation and posts the Kalkulator's decision back as a
// structured resume on the turn endpoint. One control per interrupt stage:
//   - method_review (Gate A): confirm the Leistung and select the Bauverfahren.
//   - variable_review (Gate B): accept/override every worklist leaf, tiered by confidence — the
//     surfaced tier (low-confidence + high-stakes) shown for decision, the collapsed tier (rates,
//     Stammdaten) pre-accepted but expandable and overridable.

import { useState } from 'react';
import type { ReactNode } from 'react';

import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Strong, Text } from '../../components/ui/text';
import type { CalculationResume } from '../../api/calculations';
import type { PendingInterrupt } from './hooks/useWorkspaceConversation';

// Interrupt stages, matching the backend STAGE_* constants in shared/services/calculator/state.py.
const STAGE_PROJECT_CONTEXT_REVIEW = 'project_context_review';
const STAGE_METHOD_REVIEW = 'method_review';
const STAGE_VARIABLE_REVIEW = 'variable_review';

// Location geocoding status, matching the backend ContextStatus / BAUSTELLE_* values.
const BAUSTELLE_OK = 'aufgeloest';
const BAUSTELLE_UNSICHER = 'unsicher';
const BAUSTELLE_FEHLT = 'fehlgeschlagen';

// Project-context reconcile flags, matching the backend RECONCILE_* constants.
const RECONCILE_KONFLIKT = 'konflikt';

interface PanelProps {
  payload: Record<string, unknown>;
  onResume: (decision: CalculationResume) => void;
  disabled?: boolean;
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
}

function asRecordArray(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v)
    ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
    : [];
}

function str(v: unknown): string {
  return v == null ? '' : String(v);
}

// Mirrors the backend _parse_override: accepts German convention (',' decimal, '.' thousands)
// and the dot-decimal form the proposals are pre-filled with. Empty is not numeric here —
// the caller treats it as "accept proposal" / "missing", not as an invalid override.
function isNumericInput(raw: string): boolean {
  const token = raw.trim();
  if (token === '') return false;
  const normalised = token.includes(',') ? token.replace(/\./g, '').replace(',', '.') : token;
  return /^-?(\d+\.?\d*|\.\d+)$/.test(normalised);
}

export function InterruptPanel({
  interrupt,
  onResume,
  disabled,
}: {
  interrupt: PendingInterrupt;
  onResume: (decision: CalculationResume) => void;
  disabled?: boolean;
}) {
  switch (interrupt.stage) {
    case STAGE_PROJECT_CONTEXT_REVIEW:
      return (
        <ProjectContextReview payload={interrupt.payload} onResume={onResume} disabled={disabled} />
      );
    case STAGE_METHOD_REVIEW:
      return <MethodReview payload={interrupt.payload} onResume={onResume} disabled={disabled} />;
    case STAGE_VARIABLE_REVIEW:
      return <VariableReview payload={interrupt.payload} onResume={onResume} disabled={disabled} />;
    default:
      return null;
  }
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border-t border-zinc-950/5 px-6 py-4 dark:border-white/5">
      <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{title}</div>
      <div className="pt-2">{children}</div>
    </div>
  );
}

// --- Gate A: confirm/correct the Leistung, select the Bauverfahren ----------
interface KatalogEintrag {
  leistung_key: string;
  name: string;
  kandidaten: string[];
}

function asKatalog(v: unknown): KatalogEintrag[] {
  return asRecordArray(v).map((e) => ({
    leistung_key: str(e.leistung_key),
    name: str(e.name),
    kandidaten: asStringArray(e.kandidaten),
  }));
}

interface SlotInfo {
  slot: string;
  geraet: string;
  kandidaten: { code: string; hersteller: string; modell: string }[];
}

function asRessourcen(v: unknown): Record<string, SlotInfo[]> {
  const out: Record<string, SlotInfo[]> = {};
  const rec = v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
  for (const [bvCode, slots] of Object.entries(rec)) {
    out[bvCode] = asRecordArray(slots).map((s) => ({
      slot: str(s.slot),
      geraet: str(s.geraet),
      kandidaten: asRecordArray(s.kandidaten).map((m) => ({
        code: str(m.code),
        hersteller: str(m.hersteller),
        modell: str(m.modell),
      })),
    }));
  }
  return out;
}

interface BaustoffInfo {
  code: string;
  name: string;
}

function asBaustoffe(v: unknown): BaustoffInfo[] {
  return asRecordArray(v).map((b) => ({ code: str(b.code), name: str(b.name) }));
}

interface BaustoffVorschlag {
  code: string | null;
  name: string | null;
  konfidenz: number;
  auto: boolean;
}

// BM25 material match from the LV text; null when the recipe needs no Baustoff.
function asVorschlag(v: unknown): BaustoffVorschlag | null {
  if (!v || typeof v !== 'object') return null;
  const r = v as Record<string, unknown>;
  return {
    code: r.code ? str(r.code) : null,
    name: r.name ? str(r.name) : null,
    konfidenz: typeof r.konfidenz === 'number' ? r.konfidenz : 0,
    auto: r.auto === true,
  };
}

interface LieferantAngebot {
  code: string;
  name: string;
  ort: string;
  werk_eur_pro_t: string;
  strasse_km: string;
  frei_bau_eur_pro_t: string;
}

interface LieferantenVorschlag {
  default: string | null;
  angebote: LieferantAngebot[];
}

// Ranked suppliers per material (baustoff_code -> ranked offers, cheapest delivered first); empty
// when no supplier carries the material or the location was not resolved.
function asLieferanten(v: unknown): Record<string, LieferantenVorschlag> {
  const out: Record<string, LieferantenVorschlag> = {};
  const rec = v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
  for (const [code, val] of Object.entries(rec)) {
    const r = val && typeof val === 'object' ? (val as Record<string, unknown>) : {};
    out[code] = {
      default: r.default ? str(r.default) : null,
      angebote: asRecordArray(r.angebote).map((a) => ({
        code: str(a.code),
        name: str(a.name),
        ort: str(a.ort),
        werk_eur_pro_t: str(a.werk_eur_pro_t),
        strasse_km: str(a.strasse_km),
        frei_bau_eur_pro_t: str(a.frei_bau_eur_pro_t),
      })),
    };
  }
  return out;
}

// Right-sized default machine per Ausführungsart slot, e.g. { AA_KALTFRAESE: 'WIRTGEN_W100CFI' }.
function asStringMap(v: unknown): Record<string, string> {
  if (!v || typeof v !== 'object') return {};
  return Object.fromEntries(
    Object.entries(v as Record<string, unknown>).map(([k, val]) => [k, str(val)]),
  );
}

const PICKER =
  'block w-full rounded-lg border border-zinc-950/10 bg-transparent px-3 py-1.5 text-sm dark:border-white/10 dark:bg-white/5';

function MethodReview({ payload, onResume, disabled }: PanelProps) {
  const katalog = asKatalog(payload.katalog);
  const ressourcen = asRessourcen(payload.bauverfahren_ressourcen);
  const baustoffe = asBaustoffe(payload.baustoff_katalog);
  const vorschlag = asVorschlag(payload.baustoff_vorschlag);
  const lieferantenVorschlag = asLieferanten(payload.lieferanten_vorschlag);
  const suggested = str(payload.leistung_key);
  // Pre-select the classified Leistung only when it is valid (has candidate Bauverfahren);
  // otherwise the Kalkulator must pick one from the catalog.
  const initial = katalog.find((l) => l.leistung_key === suggested && l.kandidaten.length > 0) ?? null;

  const maschinenDefault = asStringMap(payload.maschinen_default);
  // Right-sized default per slot for the classified recipe; other recipes fall back to the
  // first candidate (a recipe switch in Gate A re-derives slots client-side).
  const slotDefaults = (bvCode: string): Record<string, string> =>
    Object.fromEntries(
      (ressourcen[bvCode] ?? []).map((s) => [
        s.slot,
        maschinenDefault[s.slot] ?? s.kandidaten[0]?.code ?? '',
      ]),
    );

  const [selected, setSelected] = useState<KatalogEintrag | null>(initial);
  const [query, setQuery] = useState('');
  const [bv, setBv] = useState<string>(initial?.kandidaten[0] ?? '');
  const [maschinen, setMaschinen] = useState<Record<string, string>>(() =>
    slotDefaults(initial?.kandidaten[0] ?? ''),
  );
  const [baustoff, setBaustoff] = useState(vorschlag?.code ?? '');
  const [lieferant, setLieferant] = useState<string>(
    () => lieferantenVorschlag[vorschlag?.code ?? '']?.default ?? '',
  );

  // Switching the material switches its supplier list; default to that material's cheapest.
  const chooseBaustoff = (code: string) => {
    setBaustoff(code);
    setLieferant(lieferantenVorschlag[code]?.default ?? '');
  };
  const supplierAngebote = lieferantenVorschlag[baustoff]?.angebote ?? [];

  const chooseBv = (k: string) => {
    setBv(k);
    setMaschinen(slotDefaults(k));
  };
  const choose = (l: KatalogEintrag) => {
    setSelected(l);
    const firstBv = l.kandidaten[0] ?? '';
    setBv(firstBv);
    setMaschinen(slotDefaults(firstBv));
    setQuery('');
  };

  const matches =
    query.trim() === ''
      ? []
      : katalog
          .filter(
            (l) =>
              l.name.toLowerCase().includes(query.toLowerCase()) ||
              l.leistung_key.toLowerCase().includes(query.toLowerCase()),
          )
          .slice(0, 8);

  return (
    <Panel title="Leistung bestätigen, Bauverfahren wählen">
      {selected ? (
        <>
          <Text>
            Leistung: <Strong>{selected.name}</Strong>{' '}
            <span className="text-zinc-500">({selected.leistung_key})</span>{' '}
            <button
              type="button"
              className="text-xs text-zinc-600 underline dark:text-zinc-400"
              onClick={() => setSelected(null)}
            >
              ändern
            </button>
          </Text>
          {selected.kandidaten.length > 0 ? (
            <>
              <Text className="pt-2 text-xs">Bauverfahren wählen — die Auswahl ist hervorgehoben:</Text>
              <div className="flex flex-wrap gap-2 pt-2">
                {selected.kandidaten.map((k) => {
                  const label = `${k}${k === selected.kandidaten[0] ? ' (Standard)' : ''}`;
                  return k === bv ? (
                    <Button key={k} disabled={disabled} onClick={() => chooseBv(k)}>
                      {label}
                    </Button>
                  ) : (
                    <Button key={k} outline disabled={disabled} onClick={() => chooseBv(k)}>
                      {label}
                    </Button>
                  );
                })}
              </div>
              {(ressourcen[bv] ?? []).length > 0 ? (
                <div className="flex flex-col gap-2 pt-3">
                  <Text className="text-xs">Maschine je Geräteplatz (Standard vorausgewählt):</Text>
                  {(ressourcen[bv] ?? []).map((s) => (
                    <div key={s.slot} className="flex flex-col gap-1">
                      <Text className="text-xs text-zinc-500">{s.geraet}</Text>
                      <select
                        className={PICKER}
                        value={maschinen[s.slot] ?? ''}
                        disabled={disabled}
                        onChange={(e) => setMaschinen((w) => ({ ...w, [s.slot]: e.target.value }))}
                      >
                        {s.kandidaten.map((m) => (
                          <option key={m.code} value={m.code}>
                            {m.hersteller} {m.modell}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              ) : null}
              {vorschlag ? (
                <div className="flex flex-col gap-1 pt-3">
                  <Text className="text-xs text-zinc-500">Baustoff</Text>
                  {vorschlag.code ? (
                    <Text
                      className={`text-xs ${
                        vorschlag.auto ? 'text-zinc-500' : 'text-amber-700 dark:text-amber-400'
                      }`}
                    >
                      BM25-Vorschlag: <Strong>{vorschlag.name}</Strong> (Konfidenz{' '}
                      {(vorschlag.konfidenz * 100).toFixed(0)} %)
                      {vorschlag.auto ? ' — automatisch übernommen' : ' — bitte prüfen'}
                    </Text>
                  ) : (
                    <Text className="text-xs text-amber-700 dark:text-amber-400">
                      Rezept benötigt einen Baustoff — bitte wählen.
                    </Text>
                  )}
                  <select
                    className={PICKER}
                    value={baustoff}
                    disabled={disabled}
                    onChange={(e) => chooseBaustoff(e.target.value)}
                  >
                    <option value="">— kein Baustoff —</option>
                    {baustoffe.map((b) => (
                      <option key={b.code} value={b.code}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                  {supplierAngebote.length > 0 ? (
                    <div className="flex flex-col gap-1 pt-2">
                      <Text className="text-xs text-zinc-500">
                        Lieferant (günstigster frei Baustelle vorausgewählt)
                      </Text>
                      <select
                        className={PICKER}
                        value={lieferant}
                        disabled={disabled}
                        onChange={(e) => setLieferant(e.target.value)}
                      >
                        {supplierAngebote.map((a) => (
                          <option key={a.code} value={a.code}>
                            {a.name} ({a.ort}) — {a.frei_bau_eur_pro_t} €/t frei Baustelle · Werk{' '}
                            {a.werk_eur_pro_t} · {a.strasse_km} km
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </>
          ) : (
            <Text className="pt-2 text-xs text-amber-700 dark:text-amber-400">
              Für diese Leistung ist kein Bauverfahren hinterlegt.
            </Text>
          )}
        </>
      ) : (
        <>
          <Text className="text-xs">
            {suggested
              ? `Position nicht eindeutig zugeordnet (${suggested}). Leistung suchen und wählen:`
              : 'Leistung suchen und wählen:'}
          </Text>
          <div className="pt-2">
            <Input
              value={query}
              disabled={disabled}
              placeholder="Leistung suchen…"
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          {matches.length > 0 ? (
            <div className="mt-2 flex flex-col gap-1">
              {matches.map((l) => (
                <button
                  key={l.leistung_key}
                  type="button"
                  disabled={disabled}
                  className="rounded px-2 py-1 text-left text-sm hover:bg-zinc-950/5 dark:hover:bg-white/5"
                  onClick={() => choose(l)}
                >
                  <span className="text-zinc-900 dark:text-zinc-100">{l.name}</span>{' '}
                  <span className="text-xs text-zinc-500">{l.leistung_key}</span>
                </button>
              ))}
            </div>
          ) : query.trim() !== '' ? (
            <Text className="pt-1 text-xs text-zinc-500">Keine Treffer.</Text>
          ) : null}
        </>
      )}

      <div className="flex gap-2 pt-4">
        <Button
          disabled={disabled || !selected || !bv}
          onClick={() =>
            selected &&
            onResume({
              leistung_key: selected.leistung_key,
              bauverfahren_key: bv,
              maschinen,
              baustoff_code: baustoff || undefined,
              lieferanten: baustoff && lieferant ? { [baustoff]: lieferant } : undefined,
            })
          }
        >
          Bestätigen & weiter
        </Button>
        <Button outline disabled={disabled} onClick={() => onResume({ cancel: true })}>
          Abbrechen
        </Button>
      </div>
    </Panel>
  );
}

// --- Pre-Gate-A: confirm/override the project globals ----------------------
interface ReconcileEntry {
  flag?: string;
  chat_wert?: string;
  aktuell_wert?: string;
}

function StatusHint({ status }: { status: string }) {
  if (status === BAUSTELLE_OK) return <span className="ml-2 text-zinc-500">geokodiert</span>;
  if (status === BAUSTELLE_UNSICHER)
    return <span className="ml-2 text-amber-700 dark:text-amber-400">unsicher — bitte prüfen</span>;
  if (status === BAUSTELLE_FEHLT)
    return (
      <span className="ml-2 text-amber-700 dark:text-amber-400">nicht geokodiert — bitte prüfen</span>
    );
  return null;
}

function ContextField({
  label,
  value,
  onChange,
  status,
  conflict,
  disabled,
  numeric,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  status?: string;
  conflict?: ReconcileEntry;
  disabled?: boolean;
  numeric?: boolean;
}) {
  const isConflict = conflict?.flag === RECONCILE_KONFLIKT;
  return (
    <div className="flex flex-col gap-1">
      <Text className="text-xs text-zinc-500">
        {label}
        {status ? <StatusHint status={status} /> : null}
      </Text>
      {isConflict ? (
        <div className="flex flex-col gap-1 rounded border border-amber-500/40 p-2">
          <Text className="text-xs text-amber-700 dark:text-amber-400">
            Konflikt: Chat „{str(conflict?.chat_wert)}“ vs. gespeichert „{str(conflict?.aktuell_wert)}“
          </Text>
          <div className="flex gap-2">
            <Button outline disabled={disabled} onClick={() => onChange(str(conflict?.chat_wert))}>
              Chat übernehmen
            </Button>
            <Button outline disabled={disabled} onClick={() => onChange(str(conflict?.aktuell_wert))}>
              Gespeichert behalten
            </Button>
          </div>
        </div>
      ) : null}
      <Input
        value={value}
        disabled={disabled}
        inputMode={numeric ? 'decimal' : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function ProjectContextReview({ payload, onResume, disabled }: PanelProps) {
  const kontext =
    payload.projekt_kontext && typeof payload.projekt_kontext === 'object'
      ? (payload.projekt_kontext as Record<string, unknown>)
      : {};
  const reconcile =
    payload.reconcile && typeof payload.reconcile === 'object'
      ? (payload.reconcile as Record<string, ReconcileEntry>)
      : {};

  const [baustelle, setBaustelle] = useState(str(kontext.baustelle_location));
  const [deponie, setDeponie] = useState(str(kontext.deponie_location));
  const [length, setLength] = useState(str(kontext.strip_length_m));
  const [width, setWidth] = useState(str(kontext.strip_width_m));
  const [fraesgut, setFraesgut] = useState(str(kontext.fraesgut_klasse));

  // Only the changed fields are sent; each becomes a new version on the backend.
  const changed = (): Record<string, string> => {
    const u: Record<string, string> = {};
    if (baustelle !== str(kontext.baustelle_location)) u.baustelle_location = baustelle;
    if (deponie !== str(kontext.deponie_location)) u.deponie_location = deponie;
    if (length !== str(kontext.strip_length_m)) u.strip_length_m = length;
    if (width !== str(kontext.strip_width_m)) u.strip_width_m = width;
    if (fraesgut !== str(kontext.fraesgut_klasse)) u.fraesgut_klasse = fraesgut;
    return u;
  };

  return (
    <Panel title="Projektkontext bestätigen">
      <Text className="text-xs text-zinc-500">
        Diese Werte gelten für das ganze Projekt (Streckenabschnitt). Bestätigen oder überschreiben —
        Änderungen werden als neue Version gespeichert.
      </Text>
      <div className="flex flex-col gap-3 pt-2">
        <ContextField
          label="Baustelle (Standort)"
          value={baustelle}
          onChange={setBaustelle}
          status={str(kontext.baustelle_status)}
          conflict={reconcile.baustelle_location}
          disabled={disabled}
        />
        <ContextField
          label="Deponie / Entsorgung"
          value={deponie}
          onChange={setDeponie}
          status={str(kontext.deponie_status)}
          conflict={reconcile.deponie_location}
          disabled={disabled}
        />
        <ContextField
          label="Streckenlänge (m)"
          value={length}
          onChange={setLength}
          conflict={reconcile.strip_length_m}
          disabled={disabled}
          numeric
        />
        <ContextField
          label="Streckenbreite (m)"
          value={width}
          onChange={setWidth}
          conflict={reconcile.strip_width_m}
          disabled={disabled}
          numeric
        />
        <ContextField
          label="Fräsgutklasse"
          value={fraesgut}
          onChange={setFraesgut}
          conflict={reconcile.fraesgut_klasse}
          disabled={disabled}
          numeric
        />
        <div className="flex flex-col gap-1">
          <Text className="text-xs text-zinc-500">Entfernung zur Deponie (km, berechnet)</Text>
          <Input value={str(kontext.entfernung_deponie_km) || '—'} disabled readOnly />
        </div>
      </div>
      <div className="flex gap-2 pt-4">
        <Button disabled={disabled} onClick={() => onResume({ projekt_kontext: changed() })}>
          Bestätigen & weiter
        </Button>
      </div>
    </Panel>
  );
}

// --- Gate B: review/override every worklist leaf, tiered --------------------
const QUELLE_LABEL: Record<string, string> = {
  langtext: 'Langtext',
  rag: 'RAG',
  hitl: 'Chat/HITL',
  konstante: 'Standardwert',
  stammdaten: 'Stammdaten',
};

// Why a proposed value was overridden; the value matches the backend VariableCorrectionReason enum.
const REASON_OPTIONS: { value: string; label: string }[] = [
  { value: 'falscher_wert', label: 'Falscher Wert' },
  { value: 'falsche_quelle', label: 'Falsche Quelle / nicht gefunden' },
  { value: 'einheit', label: 'Einheit / Umrechnung' },
  { value: 'kontext_fehlt', label: 'Nicht in den Unterlagen' },
  { value: 'kalkulator_ermessen', label: 'Kalkulator-Ermessen' },
  { value: 'sonstiges', label: 'Sonstiges' },
];

const REASON_PICKER =
  'mt-1 block w-full rounded-lg border border-zinc-950/10 bg-transparent px-2 py-1 text-xs text-zinc-600 dark:border-white/10 dark:bg-white/5 dark:text-zinc-400';

function VariableRow({
  v,
  value,
  invalid,
  changed,
  reason,
  onChange,
  onReason,
  disabled,
}: {
  v: Record<string, unknown>;
  value: string;
  invalid?: boolean;
  changed?: boolean;
  reason?: string;
  onChange: (next: string) => void;
  onReason?: (reason: string) => void;
  disabled?: boolean;
}) {
  const name = str(v.name);
  const unresolved = v.wert == null;
  return (
    <div className="flex flex-col gap-1">
      <Text>
        <Strong>{str(v.bezeichnung) || name}</Strong>
        {v.einheit ? <span className="text-zinc-500"> ({str(v.einheit)})</span> : null}
        {v.hochrisiko ? (
          <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-400/15 dark:text-amber-300">
            hohes Risiko
          </span>
        ) : null}
      </Text>
      <Input
        value={value}
        disabled={disabled}
        invalid={invalid}
        inputMode="decimal"
        placeholder={unresolved ? 'Wert erforderlich' : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {invalid ? (
        <Text className="text-xs text-red-600 dark:text-red-400">
          Bitte eine Zahl eingeben (z. B. 12,5).
        </Text>
      ) : null}
      <Text className="text-xs text-zinc-500 dark:text-zinc-400">
        {name}
        {v.quelle ? ` · ${QUELLE_LABEL[str(v.quelle)] ?? str(v.quelle)}` : unresolved ? ' · ungelöst' : ''}
        {v.konfidenz != null ? ` · Konfidenz ${str(v.konfidenz)}` : ''}
        {v.beleg ? ` · ${str(v.beleg)}` : ''}
      </Text>
      {/* A changed value is an override; offer an optional reason so corrections can be analysed. */}
      {changed && onReason ? (
        <select
          className={REASON_PICKER}
          value={reason ?? ''}
          disabled={disabled}
          onChange={(e) => onReason(e.target.value)}
        >
          <option value="">Grund der Änderung (optional)…</option>
          {REASON_OPTIONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      ) : null}
    </div>
  );
}

function VariableReview({ payload, onResume, disabled }: PanelProps) {
  const surfaced = asRecordArray(payload.surfaced);
  const collapsed = asRecordArray(payload.collapsed);
  const rows = [...surfaced, ...collapsed];

  // Each input is pre-filled with the proposed value (empty when unresolved). Leaving it unchanged
  // accepts the proposal; editing it sends an override. Only changed leaves are submitted.
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(rows.map((v) => [str(v.name), v.wert == null ? '' : str(v.wert)])),
  );
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [markGroundTruth, setMarkGroundTruth] = useState(false);
  const [showRates, setShowRates] = useState(false);

  const original = (v: Record<string, unknown>) => (v.wert == null ? '' : str(v.wert));
  // A leaf whose value was edited away from its proposal — i.e. an override.
  const isChanged = (v: Record<string, unknown>) => {
    const next = (values[str(v.name)] ?? '').trim();
    return next !== '' && next !== original(v);
  };
  const overrides = () => {
    const out: Record<string, unknown> = {};
    for (const v of rows) {
      if (isChanged(v)) out[str(v.name)] = (values[str(v.name)] ?? '').trim();
    }
    return out;
  };
  // Reasons only for changed leaves that have one picked; optional, so absent is fine.
  const pickedReasons = () => {
    const out: Record<string, string> = {};
    for (const v of rows) {
      const name = str(v.name);
      if (isChanged(v) && reasons[name]) out[name] = reasons[name];
    }
    return out;
  };
  // A non-empty value that isn't a number — block submission so the backend never sees garbage.
  const invalid = (name: string) => {
    const raw = (values[name] ?? '').trim();
    return raw !== '' && !isNumericInput(raw);
  };
  const hasInvalid = rows.some((v) => invalid(str(v.name)));
  const missing = surfaced.some(
    (v) => v.wert == null && (values[str(v.name)] ?? '').trim() === '',
  );
  const set = (name: string) => (next: string) => setValues((s) => ({ ...s, [name]: next }));
  const setReason = (name: string) => (next: string) =>
    setReasons((s) => ({ ...s, [name]: next }));

  const submit = () => {
    const reasonMap = pickedReasons();
    onResume({
      overrides: overrides(),
      ...(Object.keys(reasonMap).length > 0 ? { reasons: reasonMap } : {}),
      ...(markGroundTruth ? { mark_as_ground_truth: true } : {}),
    });
  };

  return (
    <Panel title="Variablen prüfen">
      <Text className="text-xs">
        Geprüft werden zuerst unsichere und besonders preiswirksame Eingaben. Sätze und Stammdaten
        sind vorab akzeptiert, lassen sich aber einblenden und überschreiben.
      </Text>

      {surfaced.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 pt-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
          {surfaced.map((v) => (
            <VariableRow
              key={str(v.name)}
              v={v}
              value={values[str(v.name)] ?? ''}
              invalid={invalid(str(v.name))}
              changed={isChanged(v)}
              reason={reasons[str(v.name)]}
              onChange={set(str(v.name))}
              onReason={setReason(str(v.name))}
              disabled={disabled}
            />
          ))}
        </div>
      ) : (
        <Text className="pt-3 text-xs">Keine unsicheren Eingaben — bitte bestätigen.</Text>
      )}

      {collapsed.length > 0 ? (
        <div className="pt-3">
          <button
            type="button"
            className="text-xs font-medium text-zinc-600 underline dark:text-zinc-400"
            onClick={() => setShowRates((s) => !s)}
          >
            {showRates ? 'Sätze & Stammdaten ausblenden' : `Sätze & Stammdaten anzeigen (${collapsed.length})`}
          </button>
          {showRates ? (
            <div className="grid grid-cols-1 gap-3 pt-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
              {collapsed.map((v) => (
                <VariableRow
                  key={str(v.name)}
                  v={v}
                  value={values[str(v.name)] ?? ''}
                  invalid={invalid(str(v.name))}
                  onChange={set(str(v.name))}
                  disabled={disabled}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="pt-4">
        <label className="flex items-center gap-2 pb-3 text-xs text-zinc-700 dark:text-zinc-300">
          <input
            type="checkbox"
            checked={markGroundTruth}
            disabled={disabled}
            onChange={(e) => setMarkGroundTruth(e.target.checked)}
            className="h-4 w-4 rounded border-zinc-300 dark:border-zinc-600"
          />
          Als Ground Truth speichern (geprüfte Werte als Referenz sichern)
        </label>
        <Button disabled={disabled || missing || hasInvalid} onClick={submit}>
          Werte bestätigen & berechnen
        </Button>
        {hasInvalid ? (
          <Text className="pt-1 text-xs text-red-600 dark:text-red-400">
            Bitte ungültige Werte korrigieren.
            {!showRates && collapsed.some((v) => invalid(str(v.name)))
              ? ' Ein Wert unter „Sätze & Stammdaten“ ist ungültig — bitte einblenden.'
              : ''}
          </Text>
        ) : missing ? (
          <Text className="pt-1 text-xs text-amber-700 dark:text-amber-400">
            Bitte alle erforderlichen Werte eintragen.
          </Text>
        ) : null}
      </div>
    </Panel>
  );
}
