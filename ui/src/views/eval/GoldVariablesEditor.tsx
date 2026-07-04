// Inline editor for one gold row's variables. Edits are drafted locally and
// saved as one PUT (the parent keys this component by updated_at, so a
// successful save remounts it on fresh server state). The add-variable picker
// offers only worklist names the gold doesn't cover yet (missing_variables) —
// the backend rejects anything outside the worklist. Saving unchanged content
// is the "Gold neu bestätigen" re-stamp for stale rows.

import { useState } from 'react';
import { XMarkIcon } from '@heroicons/react/16/solid';
import clsx from 'clsx';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Select } from '../../components/ui/select';
import { Text } from '../../components/ui/text';
import type {
  GoldVariable,
  GroundTruthRead,
  GroundTruthUpsert,
} from '../../types/generated';

const ART_EINGABE = 'eingabe';
const QUELLE_HITL = 'hitl';

type Draft = Record<string, GoldVariable>;

function stable(draft: Draft): string {
  return JSON.stringify(
    Object.entries(draft).sort(([a], [b]) => a.localeCompare(b)),
  );
}

export function GoldVariablesEditor({
  row,
  saving,
  errorMessage,
  onSave,
}: {
  row: GroundTruthRead;
  saving: boolean;
  errorMessage: string | null;
  onSave: (body: GroundTruthUpsert) => void;
}) {
  const [draft, setDraft] = useState<Draft>(row.gold_variables);
  const dirty = stable(draft) !== stable(row.gold_variables);
  const extra = new Set(row.extra_variables ?? []);
  const addable = (row.missing_variables ?? []).filter((n) => !(n in draft));

  const setField = (name: string, field: keyof GoldVariable, value: string) =>
    setDraft((d) => ({
      ...d,
      [name]: { ...d[name], [field]: value || null },
    }));

  const removeVariable = (name: string) =>
    setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => k !== name)));

  const addVariable = (name: string) =>
    setDraft((d) => ({ ...d, [name]: { wert: null, art: null } }));

  const submit = () =>
    onSave({
      leistung_key: row.leistung_key,
      bauverfahren_key: row.bauverfahren_key ?? null,
      gold_variables: draft,
    });

  return (
    <div className="flex flex-col gap-3 py-2">
      {row.stale && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
          {row.recipe_missing ?
            <>
              Rezept <span className="font-mono">{row.leistung_key}</span>
              {row.bauverfahren_key && (
                <>
                  {' / '}
                  <span className="font-mono">{row.bauverfahren_key}</span>
                </>
              )}{' '}
              ist nicht mehr im Katalog — Gold prüfen oder löschen.
            </>
          : <>
              Rezept-Worklist hat sich geändert.
              {(row.missing_variables ?? []).length > 0 && (
                <>
                  {' '}
                  Nicht im Gold:{' '}
                  <span className="font-mono">
                    {(row.missing_variables ?? []).join(', ')}
                  </span>
                  .
                </>
              )}
              {(row.extra_variables ?? []).length > 0 && (
                <>
                  {' '}
                  Nicht mehr in der Worklist (vor dem Bestätigen entfernen):{' '}
                  <span className="font-mono">
                    {(row.extra_variables ?? []).join(', ')}
                  </span>
                  .
                </>
              )}
            </>
          }
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs font-medium tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
              <th className="py-1.5 pr-4">Variable</th>
              <th className="py-1.5 pr-4">Wert</th>
              <th className="py-1.5 pr-4">Einheit</th>
              <th className="py-1.5 pr-4">Art</th>
              <th className="py-1.5 pr-4">Quelle</th>
              <th className="w-8 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {Object.entries(draft).map(([name, v]) => (
              <tr
                key={name}
                className="border-t border-zinc-950/5 dark:border-white/5"
              >
                <td
                  className={clsx(
                    'py-1.5 pr-4 font-mono text-xs',
                    extra.has(name) && 'text-amber-600 dark:text-amber-400',
                  )}
                >
                  {name}
                </td>
                <td className="py-1.5 pr-4">
                  <Input
                    className="max-w-28 font-mono"
                    value={v.wert ?? ''}
                    disabled={saving}
                    onChange={(e) => setField(name, 'wert', e.target.value)}
                    aria-label={`Wert ${name}`}
                  />
                </td>
                <td className="py-1.5 pr-4">
                  <Input
                    className="max-w-20"
                    value={v.einheit ?? ''}
                    disabled={saving}
                    onChange={(e) => setField(name, 'einheit', e.target.value)}
                    aria-label={`Einheit ${name}`}
                  />
                </td>
                <td className="py-1.5 pr-4">
                  <Badge color={v.art === ART_EINGABE ? 'blue' : 'zinc'}>
                    {v.art ?? '—'}
                  </Badge>
                </td>
                <td className="py-1.5 pr-4 text-xs text-zinc-500">
                  {v.quelle ?? '—'}
                  {v.quelle === QUELLE_HITL && (
                    <Badge
                      color="purple"
                      className="ml-1.5"
                    >
                      Gate B
                    </Badge>
                  )}
                </td>
                <td className="py-1.5">
                  <Button
                    plain
                    aria-label={`${name} entfernen`}
                    disabled={saving}
                    onClick={() => removeVariable(name)}
                  >
                    <XMarkIcon />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {addable.length > 0 && (
        <div className="max-w-xs">
          <Select
            value=""
            disabled={saving}
            aria-label="Variable hinzufügen"
            onChange={(e) => {
              if (e.target.value) addVariable(e.target.value);
            }}
          >
            <option value="">Variable hinzufügen (aus Rezept-Worklist)…</option>
            {addable.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </div>
      )}

      {errorMessage && (
        <Text className="text-xs text-red-600 dark:text-red-400">
          {errorMessage}
        </Text>
      )}

      <div className="flex items-center gap-2">
        <Button
          disabled={saving || (!dirty && !row.stale)}
          onClick={submit}
        >
          {!dirty && row.stale ? 'Gold neu bestätigen' : 'Speichern'}
        </Button>
        <Button
          plain
          disabled={saving || !dirty}
          onClick={() => setDraft(row.gold_variables)}
        >
          Verwerfen
        </Button>
      </div>
    </div>
  );
}
