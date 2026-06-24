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
const STAGE_METHOD_REVIEW = 'method_review';
const STAGE_VARIABLE_REVIEW = 'variable_review';

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

function MethodReview({ payload, onResume, disabled }: PanelProps) {
  const katalog = asKatalog(payload.katalog);
  const suggested = str(payload.leistung_key);
  // Pre-select the classified Leistung only when it is valid (has candidate Bauverfahren);
  // otherwise the Kalkulator must pick one from the catalog.
  const initial = katalog.find((l) => l.leistung_key === suggested && l.kandidaten.length > 0) ?? null;

  const [selected, setSelected] = useState<KatalogEintrag | null>(initial);
  const [query, setQuery] = useState('');
  const [bv, setBv] = useState<string>(initial?.kandidaten[0] ?? '');

  const choose = (l: KatalogEintrag) => {
    setSelected(l);
    setBv(l.kandidaten[0] ?? '');
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
                    <Button key={k} disabled={disabled} onClick={() => setBv(k)}>
                      {label}
                    </Button>
                  ) : (
                    <Button key={k} outline disabled={disabled} onClick={() => setBv(k)}>
                      {label}
                    </Button>
                  );
                })}
              </div>
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
          onClick={() => selected && onResume({ leistung_key: selected.leistung_key, bauverfahren_key: bv })}
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

// --- Gate B: review/override every worklist leaf, tiered --------------------
const QUELLE_LABEL: Record<string, string> = {
  langtext: 'Langtext',
  rag: 'RAG',
  hitl: 'Chat/HITL',
  konstante: 'Standardwert',
  stammdaten: 'Stammdaten',
};

function VariableRow({
  v,
  value,
  onChange,
  disabled,
}: {
  v: Record<string, unknown>;
  value: string;
  onChange: (next: string) => void;
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
        placeholder={unresolved ? 'Wert erforderlich' : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      <Text className="text-xs text-zinc-500 dark:text-zinc-400">
        {name}
        {v.quelle ? ` · ${QUELLE_LABEL[str(v.quelle)] ?? str(v.quelle)}` : unresolved ? ' · ungelöst' : ''}
        {v.konfidenz != null ? ` · Konfidenz ${str(v.konfidenz)}` : ''}
        {v.beleg ? ` · ${str(v.beleg)}` : ''}
      </Text>
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
  const [showRates, setShowRates] = useState(false);

  const original = (v: Record<string, unknown>) => (v.wert == null ? '' : str(v.wert));
  const overrides = () => {
    const out: Record<string, unknown> = {};
    for (const v of rows) {
      const name = str(v.name);
      const next = (values[name] ?? '').trim();
      if (next !== '' && next !== original(v)) out[name] = next;
    }
    return out;
  };
  const missing = surfaced.some(
    (v) => v.wert == null && (values[str(v.name)] ?? '').trim() === '',
  );
  const set = (name: string) => (next: string) => setValues((s) => ({ ...s, [name]: next }));

  return (
    <Panel title="Variablen prüfen">
      <Text className="text-xs">
        Geprüft werden zuerst unsichere und besonders preiswirksame Eingaben. Sätze und Stammdaten
        sind vorab akzeptiert, lassen sich aber einblenden und überschreiben.
      </Text>

      {surfaced.length > 0 ? (
        <div className="flex flex-col gap-3 pt-3">
          {surfaced.map((v) => (
            <VariableRow
              key={str(v.name)}
              v={v}
              value={values[str(v.name)] ?? ''}
              onChange={set(str(v.name))}
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
            <div className="flex flex-col gap-3 pt-3">
              {collapsed.map((v) => (
                <VariableRow
                  key={str(v.name)}
                  v={v}
                  value={values[str(v.name)] ?? ''}
                  onChange={set(str(v.name))}
                  disabled={disabled}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="pt-4">
        <Button disabled={disabled || missing} onClick={() => onResume({ overrides: overrides() })}>
          Werte bestätigen & berechnen
        </Button>
        {missing ? (
          <Text className="pt-1 text-xs text-amber-700 dark:text-amber-400">
            Bitte alle erforderlichen Werte eintragen.
          </Text>
        ) : null}
      </div>
    </Panel>
  );
}
