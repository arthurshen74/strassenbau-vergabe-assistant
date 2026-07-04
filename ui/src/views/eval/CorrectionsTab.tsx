// The Korrekturen tab: read-only error-analysis over Gate-B overrides. The
// stacked-bar rollup shows which variables the model gets wrong and why; the
// table lists each correction (proposal vs. final, reason, note). Corrections
// are only ever written by the EKT Gate-B flow — there is no editing here.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { LockClosedIcon } from '@heroicons/react/16/solid';
import {
  reasonKind,
  useCorrections,
  useCorrectionsSummary,
} from '../../api/variableCorrections';
import { Badge } from '../../components/ui/badge';
import { Select } from '../../components/ui/select';
import { Switch, SwitchField } from '../../components/ui/switch';
import { Label } from '../../components/ui/fieldset';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/ui/table';
import { Text } from '../../components/ui/text';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import { formatTimestamp } from '../../lib/format';
import type { VariableCorrection } from '../../types/generated';
import { CorrectionsAnalysis } from './CorrectionsAnalysis';

// Values match VariableCorrectionReason; labels mirror the Gate-B reason chips.
const REASON_LABELS: Record<string, string> = {
  falscher_wert: 'Falscher Wert',
  falsche_quelle: 'Falsche Quelle / nicht gefunden',
  einheit: 'Einheit / Umrechnung',
  kontext_fehlt: 'Nicht in den Unterlagen',
  kalkulator_ermessen: 'Kalkulator-Ermessen',
  sonstiges: 'Sonstiges',
};

const KIND_BADGE: Record<string, 'red' | 'amber' | 'purple' | 'zinc'> = {
  model: 'red',
  gap: 'amber',
  preference: 'purple',
  other: 'zinc',
};

function ReasonBadge({ reason }: { reason: VariableCorrection['reason'] }) {
  if (!reason) return <span className="text-zinc-400">—</span>;
  return <Badge color={KIND_BADGE[reasonKind(reason)]}>{REASON_LABELS[reason]}</Badge>;
}

export function CorrectionsTab({ projectUuid }: { projectUuid: string }) {
  const [variableName, setVariableName] = useState('');
  const [reason, setReason] = useState('');
  const [onlyModelErrors, setOnlyModelErrors] = useState(false);
  const summary = useCorrectionsSummary(projectUuid);
  const corrections = useCorrections(projectUuid, {
    variableName: variableName || undefined,
    reason: reason || undefined,
  });

  if (corrections.isLoading || summary.isLoading) return <LoadingState />;
  if (corrections.isError) {
    return (
      <ErrorState
        message={(corrections.error as Error).message}
        onRetry={() => corrections.refetch()}
      />
    );
  }

  const variableOptions = [
    ...new Set((summary.data ?? []).map((r) => r.variable_name)),
  ].sort();
  const rows = (corrections.data ?? []).filter(
    (c) => !onlyModelErrors || reasonKind(c.reason) === 'model',
  );

  if ((summary.data ?? []).length === 0) {
    return (
      <Text className="text-sm">
        Noch keine Korrekturen. Sie entstehen automatisch bei jeder
        Wert-Änderung in der Gate-B-Prüfung.
      </Text>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 rounded-lg border border-zinc-950/10 bg-zinc-50 px-3 py-2 text-xs text-zinc-500 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-400">
        <LockClosedIcon className="h-3.5 w-3.5 shrink-0" />
        Nur lesend — Korrekturen entstehen ausschließlich im EKT-Flow (Gate B).
        Sie sind das Fehleranalyse-Protokoll, keine kuratierbaren Daten.
      </div>

      <CorrectionsAnalysis rows={summary.data ?? []} />

      <div className="flex flex-wrap items-center gap-3">
        <Select
          className="max-w-56"
          value={variableName}
          onChange={(e) => setVariableName(e.target.value)}
          aria-label="Nach Variable filtern"
        >
          <option value="">Variable: Alle</option>
          {variableOptions.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </Select>
        <Select
          className="max-w-64"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          aria-label="Nach Grund filtern"
        >
          <option value="">Grund: Alle</option>
          {Object.entries(REASON_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <SwitchField className="ml-auto">
          <Label>Nur Modellfehler</Label>
          <Switch
            checked={onlyModelErrors}
            onChange={setOnlyModelErrors}
            aria-label="Nur Modellfehler"
          />
        </SwitchField>
      </div>

      {rows.length === 0 ?
        <Text className="text-sm">Keine Korrekturen für diese Filter.</Text>
      : <Table className="[--gutter:--spacing(4)]">
          <TableHead>
            <TableRow>
              <TableHeader>Zeit</TableHeader>
              <TableHeader>OZ</TableHeader>
              <TableHeader>Variable</TableHeader>
              <TableHeader>Vorschlag → Final</TableHeader>
              <TableHeader>Vorschlags-Quelle</TableHeader>
              <TableHeader>Grund</TableHeader>
              <TableHeader>Notiz</TableHeader>
              <TableHeader />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((c) => (
              <TableRow key={c.correction_uuid}>
                <TableCell className="text-xs whitespace-nowrap text-zinc-500 tabular-nums">
                  {formatTimestamp(c.created_at)}
                </TableCell>
                <TableCell className="font-mono text-xs text-zinc-500">
                  {c.oz ?? '—'}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {c.variable_name}
                </TableCell>
                <TableCell className="font-mono text-xs whitespace-nowrap tabular-nums">
                  <span className="text-zinc-400 line-through">
                    {c.proposed_wert ?? '—'}
                  </span>
                  <span className="px-1.5 text-zinc-400">→</span>
                  <span className="font-semibold">{c.final_wert}</span>
                </TableCell>
                <TableCell className="text-xs text-zinc-500">
                  {c.proposed_quelle ?? '—'}
                  {c.proposed_konfidenz && ` · ${c.proposed_konfidenz}`}
                </TableCell>
                <TableCell>
                  <ReasonBadge reason={c.reason} />
                </TableCell>
                <TableCell className="max-w-64 truncate text-xs text-zinc-500">
                  {c.note ?? ''}
                </TableCell>
                <TableCell>
                  {c.conversation_uuid && (
                    <Link
                      to={`/c/${c.conversation_uuid}`}
                      className="text-sm whitespace-nowrap text-blue-600 hover:underline dark:text-blue-400"
                    >
                      Konversation
                    </Link>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      }
    </div>
  );
}
