// Renders the control for a paused EKT calculator run and posts the Kalkulator's decision back via
// the resume endpoint. One control per interrupt stage: pick the Leistung (classification), confirm
// or correct the assumed drivers (driver confirmation), or act on the EKT (review).

import { useState } from 'react';
import type { ReactNode } from 'react';

import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Strong, Text } from '../../components/ui/text';
import type { CalculationResume } from '../../api/calculations';
import type { PendingInterrupt } from './useCalculatorConversation';

// Interrupt stages, matching the backend STAGE_* constants in shared/services/calculator/graph.py.
const STAGE_CLASSIFICATION = 'classification';
const STAGE_DRIVER_CONFIRMATION = 'driver_confirmation';
const STAGE_EKT_REVIEW = 'ekt_review';

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

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : null;
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
    case STAGE_CLASSIFICATION:
      return (
        <ClassificationGate payload={interrupt.payload} onResume={onResume} disabled={disabled} />
      );
    case STAGE_DRIVER_CONFIRMATION:
      return <DriverConfirm payload={interrupt.payload} onResume={onResume} disabled={disabled} />;
    case STAGE_EKT_REVIEW:
      return <EktReview payload={interrupt.payload} onResume={onResume} disabled={disabled} />;
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

function ClassificationGate({ payload, onResume, disabled }: PanelProps) {
  const options = asStringArray(payload.options);
  const suggestion = str(payload.agent_suggestion);
  return (
    <Panel title="Confirm the Leistung">
      <Text>
        Suggested: <Strong>{suggestion}</Strong>
        {payload.confidence != null ? ` (${str(payload.confidence)})` : ''}
      </Text>
      {payload.notes ? <Text className="text-xs">{str(payload.notes)}</Text> : null}
      <div className="flex flex-wrap gap-2 pt-2">
        {options.map((opt) =>
          opt === suggestion ? (
            <Button key={opt} disabled={disabled} onClick={() => onResume({ work_type: opt })}>
              {opt} (suggested)
            </Button>
          ) : (
            <Button key={opt} outline disabled={disabled} onClick={() => onResume({ work_type: opt })}>
              {opt}
            </Button>
          ),
        )}
      </div>
    </Panel>
  );
}

function DriverConfirm({ payload, onResume, disabled }: PanelProps) {
  const confirm = asRecordArray(payload.confirm);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const submit = () => {
    const cleaned: Record<string, unknown> = {};
    for (const [id, value] of Object.entries(overrides)) {
      if (value.trim() !== '') cleaned[id] = value.trim();
    }
    onResume({ drivers: cleaned });
  };
  return (
    <Panel title="Confirm assumed drivers">
      <div className="flex flex-col gap-3">
        {confirm.map((d) => {
          const id = str(d.id);
          return (
            <div key={id} className="flex flex-col gap-1">
              <Text>
                <Strong>{id}</Strong> = {str(d.value)} {str(d.einheit)}
              </Text>
              {d.description ? <Text className="text-xs">{str(d.description)}</Text> : null}
              <Input
                placeholder={`accept ${str(d.value)} or type a correction`}
                value={overrides[id] ?? ''}
                disabled={disabled}
                onChange={(e) => setOverrides((o) => ({ ...o, [id]: e.target.value }))}
              />
            </div>
          );
        })}
      </div>
      <div className="pt-3">
        <Button disabled={disabled} onClick={submit}>
          Confirm drivers
        </Button>
      </div>
    </Panel>
  );
}

function EktReview({ payload, onResume, disabled }: PanelProps) {
  const actions = asStringArray(payload.actions);
  const ekt = asRecord(payload.ekt);
  return (
    <Panel title="Review the EKT">
      {ekt ? (
        <Text>
          Total <Strong>{str(ekt.total_eur)} EUR</Strong> → {str(ekt.per_unit_eur)} EUR/
          {str(ekt.einheit)}
        </Text>
      ) : null}
      <div className="flex flex-wrap gap-2 pt-2">
        {actions.map((action) =>
          action === 'approve' ? (
            <Button key={action} disabled={disabled} onClick={() => onResume({ action })}>
              {action}
            </Button>
          ) : (
            <Button key={action} outline disabled={disabled} onClick={() => onResume({ action })}>
              {action}
            </Button>
          ),
        )}
      </div>
    </Panel>
  );
}
