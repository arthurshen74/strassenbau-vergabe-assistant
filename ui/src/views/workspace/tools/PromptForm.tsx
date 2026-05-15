// Editable form for appending a new prompt version. Custom rather than
// generic-schema-driven because a few fields need careful UX:
//   - system_prompt is a tall textarea (the workhorse field) and we want
//     it to feel comfortable to edit;
//   - dimensions is an array of objects (only meaningful for evaluator
//     prompts) with min/max constraints between scale_min and scale_max;
//   - the float fields have hard ranges (0..2 for temperature, 0..1 for
//     top_p / min_p) that we want to surface inline.
//
// The form starts seeded from `initialVersion` (the latest version) and
// produces an `EditPromptBody` containing only the fields the user
// actually changed — that's what edit_prompt expects (partial-update,
// inherits everything else from the latest).

import { useMemo, useState } from 'react';
import { Heading } from '../../../components/ui/heading';
import { Input } from '../../../components/ui/input';
import { Textarea } from '../../../components/ui/textarea';
import { Select } from '../../../components/ui/select';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import {
  Field,
  Fieldset,
  Label,
  Legend,
} from '../../../components/ui/fieldset';
import { PlusIcon, XMarkIcon } from '@heroicons/react/16/solid';
import type {
  EditPromptBody,
  EvalDimensionDTO,
  PromptDTO,
} from '../../../types/generated';

type ApiType = PromptDTO['api_type'];
const API_TYPES: ApiType[] = ['openai_chat', 'anthropic_messages'];

interface PromptFormState {
  api_type: ApiType;
  api_base_url: string;
  model_name: string;
  system_prompt: string;
  initial_assistant_message: string;
  temperature: string;
  top_p: string;
  min_p: string;
  /**
   * `null` means "no dimensions on this prompt" (utility/dispatcher).
   * An empty array means "this is a dimensions-bearing prompt with no
   * dimensions yet". The form lets the user toggle between these.
   */
  dimensions: EvalDimensionDTO[] | null;
}

function fromVersion(v: PromptDTO): PromptFormState {
  return {
    api_type: v.api_type,
    api_base_url: v.api_base_url,
    model_name: v.model_name,
    system_prompt: v.system_prompt,
    initial_assistant_message: v.initial_assistant_message ?? '',
    temperature: String(v.temperature),
    top_p: String(v.top_p),
    min_p: v.min_p != null ? String(v.min_p) : '',
    dimensions: v.dimensions
      ? v.dimensions.map((d) => ({ ...d }))
      : null,
  };
}

function diff(
  state: PromptFormState,
  initial: PromptDTO,
): { body: EditPromptBody; isEmpty: boolean; error?: string } {
  const body: EditPromptBody = {};

  // String fields: send only when the trimmed value differs from the
  // existing one. We don't normalize whitespace beyond trimming — long
  // system prompts contain meaningful indentation we shouldn't touch.
  if (state.api_type !== initial.api_type) body.api_type = state.api_type;
  if (state.api_base_url !== initial.api_base_url)
    body.api_base_url = state.api_base_url;
  if (state.model_name !== initial.model_name)
    body.model_name = state.model_name;
  if (state.system_prompt !== initial.system_prompt)
    body.system_prompt = state.system_prompt;

  const initialMsg = initial.initial_assistant_message ?? '';
  if (state.initial_assistant_message !== initialMsg) {
    body.initial_assistant_message =
      state.initial_assistant_message.trim() === ''
        ? null
        : state.initial_assistant_message;
  }

  // Float fields: parse, validate ranges, send only on change.
  const parseFloatField = (
    v: string,
    min: number,
    max: number,
    label: string,
  ): { ok: true; value: number } | { ok: false; error: string } => {
    const n = Number(v);
    if (Number.isNaN(n))
      return { ok: false, error: `${label} must be a number.` };
    if (n < min || n > max)
      return {
        ok: false,
        error: `${label} must be between ${min} and ${max}.`,
      };
    return { ok: true, value: n };
  };

  const t = parseFloatField(state.temperature, 0, 2, 'Temperature');
  if (!t.ok) return { body, isEmpty: false, error: t.error };
  if (t.value !== initial.temperature) body.temperature = t.value;

  const tp = parseFloatField(state.top_p, 0, 1, 'top_p');
  if (!tp.ok) return { body, isEmpty: false, error: tp.error };
  if (tp.value !== initial.top_p) body.top_p = tp.value;

  // min_p is optional; empty string means "leave unset / clear".
  if (state.min_p === '') {
    if (initial.min_p != null) body.min_p = null;
  } else {
    const mp = parseFloatField(state.min_p, 0, 1, 'min_p');
    if (!mp.ok) return { body, isEmpty: false, error: mp.error };
    if (mp.value !== initial.min_p) body.min_p = mp.value;
  }

  // Dimensions: only send when the user has actually changed them. We
  // serialize current and initial through JSON to compare structurally.
  const initialDims = initial.dimensions ?? null;
  if (
    JSON.stringify(state.dimensions) !== JSON.stringify(initialDims)
  ) {
    body.dimensions = state.dimensions;
  }

  const isEmpty = Object.keys(body).length === 0;
  return { body, isEmpty };
}

export interface PromptFormProps {
  initialVersion: PromptDTO;
  heading?: string;
  submitLabel?: string;
  submitting?: boolean;
  errorMessage?: string | null;
  onSubmit: (body: EditPromptBody) => Promise<void> | void;
  onCancel: () => void;
}

export function PromptForm({
  initialVersion,
  heading = 'Edit prompt',
  submitLabel = 'Save changes',
  submitting = false,
  errorMessage,
  onSubmit,
  onCancel,
}: PromptFormProps) {
  const [state, setState] = useState<PromptFormState>(() =>
    fromVersion(initialVersion),
  );
  const [localError, setLocalError] = useState<string | null>(null);

  const update = <K extends keyof PromptFormState>(
    key: K,
    value: PromptFormState[K],
  ) => setState((s) => ({ ...s, [key]: value }));

  const updateDim = (
    idx: number,
    patch: Partial<EvalDimensionDTO>,
  ) =>
    setState((s) => ({
      ...s,
      dimensions:
        s.dimensions?.map((d, i) => (i === idx ? { ...d, ...patch } : d)) ??
        null,
    }));

  const addDim = () =>
    setState((s) => ({
      ...s,
      dimensions: [
        ...(s.dimensions ?? []),
        { name: '', description: '', scale_min: 1, scale_max: 5 },
      ],
    }));

  const removeDim = (idx: number) =>
    setState((s) => ({
      ...s,
      dimensions: s.dimensions?.filter((_, i) => i !== idx) ?? null,
    }));

  const enableDimensions = () =>
    setState((s) => ({ ...s, dimensions: s.dimensions ?? [] }));

  const disableDimensions = () =>
    setState((s) => ({ ...s, dimensions: null }));

  // Compute the diff once per render so we can disable Save when there's
  // nothing to send (mirrors the server's "at least one field" rule).
  const computed = useMemo(
    () => diff(state, initialVersion),
    [state, initialVersion],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (computed.error) {
      setLocalError(computed.error);
      return;
    }
    if (computed.isEmpty) {
      setLocalError('Change at least one field before saving.');
      return;
    }
    await onSubmit(computed.body);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <Heading level={4}>{heading}</Heading>
        <Badge color="zinc">
          v{initialVersion.version} · saving as v{initialVersion.version + 1}
        </Badge>
      </div>

      <Fieldset>
        <Legend>Provider & model</Legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field>
            <Label>API type</Label>
            <Select
              value={state.api_type}
              onChange={(e) => update('api_type', e.target.value as ApiType)}
            >
              {API_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
          <Field>
            <Label>Model name</Label>
            <Input
              value={state.model_name}
              onChange={(e) => update('model_name', e.target.value)}
            />
          </Field>
          <Field className="sm:col-span-2">
            <Label>API base URL</Label>
            <Input
              value={state.api_base_url}
              onChange={(e) => update('api_base_url', e.target.value)}
            />
          </Field>
        </div>
      </Fieldset>

      <Fieldset>
        <Legend>System prompt</Legend>
        <Field>
          <Textarea
            value={state.system_prompt}
            onChange={(e) => update('system_prompt', e.target.value)}
            rows={14}
            className="font-mono text-xs"
          />
        </Field>
        <Field>
          <Label>Initial assistant message (optional)</Label>
          <Textarea
            value={state.initial_assistant_message}
            onChange={(e) =>
              update('initial_assistant_message', e.target.value)
            }
            rows={2}
            placeholder="Empty if the assistant should wait for the first user turn."
          />
        </Field>
      </Fieldset>

      <Fieldset>
        <Legend>Sampling</Legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field>
            <Label>Temperature (0–2)</Label>
            <Input
              type="number"
              step={0.05}
              min={0}
              max={2}
              value={state.temperature}
              onChange={(e) => update('temperature', e.target.value)}
            />
          </Field>
          <Field>
            <Label>top_p (0–1)</Label>
            <Input
              type="number"
              step={0.05}
              min={0}
              max={1}
              value={state.top_p}
              onChange={(e) => update('top_p', e.target.value)}
            />
          </Field>
          <Field>
            <Label>min_p (0–1, optional)</Label>
            <Input
              type="number"
              step={0.05}
              min={0}
              max={1}
              value={state.min_p}
              onChange={(e) => update('min_p', e.target.value)}
              placeholder="leave blank to clear"
            />
          </Field>
        </div>
      </Fieldset>

      <Fieldset>
        <Legend>
          Dimensions{' '}
          <span className="text-xs font-normal text-zinc-500">
            (only used by evaluator prompts)
          </span>
        </Legend>
        {state.dimensions === null ? (
          <div className="flex items-center gap-2">
            <Text>This prompt has no scoring dimensions.</Text>
            <Button type="button" outline onClick={enableDimensions}>
              Add dimensions
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {state.dimensions.length === 0 && (
              <div className="text-xs text-zinc-500">
                No dimensions yet.
              </div>
            )}
            {state.dimensions.map((d, i) => (
              <div
                key={i}
                className="grid grid-cols-1 gap-2 rounded border border-zinc-950/5 p-2 sm:grid-cols-12 dark:border-white/10"
              >
                <div className="sm:col-span-3">
                  <Input
                    aria-label={`Dimension ${i + 1} name`}
                    value={d.name}
                    onChange={(e) => updateDim(i, { name: e.target.value })}
                    placeholder="Name"
                  />
                </div>
                <div className="sm:col-span-5">
                  <Input
                    aria-label={`Dimension ${i + 1} description`}
                    value={d.description}
                    onChange={(e) =>
                      updateDim(i, { description: e.target.value })
                    }
                    placeholder="Description"
                  />
                </div>
                <div className="sm:col-span-2">
                  <Input
                    aria-label={`Dimension ${i + 1} scale_min`}
                    type="number"
                    value={d.scale_min}
                    onChange={(e) =>
                      updateDim(i, { scale_min: Number(e.target.value) })
                    }
                  />
                </div>
                <div className="sm:col-span-1">
                  <Input
                    aria-label={`Dimension ${i + 1} scale_max`}
                    type="number"
                    value={d.scale_max}
                    onChange={(e) =>
                      updateDim(i, { scale_max: Number(e.target.value) })
                    }
                  />
                </div>
                <div className="flex items-center justify-end sm:col-span-1">
                  <Button
                    type="button"
                    plain
                    onClick={() => removeDim(i)}
                    aria-label={`Remove dimension ${i + 1}`}
                  >
                    <XMarkIcon />
                  </Button>
                </div>
              </div>
            ))}
            <div className="flex items-center gap-2">
              <Button type="button" outline onClick={addDim}>
                <PlusIcon />
                Add dimension
              </Button>
              <Button type="button" plain onClick={disableDimensions}>
                Remove all (set to none)
              </Button>
            </div>
          </div>
        )}
      </Fieldset>

      {(localError || errorMessage) && (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-700/50 dark:bg-red-950/30 dark:text-red-300">
          {localError || errorMessage}
        </div>
      )}

      <div className="flex items-center justify-end gap-2">
        <Button type="button" plain onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={submitting || computed.isEmpty || !!computed.error}
        >
          {submitting ? 'Saving…' : submitLabel}
        </Button>
      </div>
    </form>
  );
}

// Local Text helper to avoid a stray import — the prompt form only uses
// it once, in the dimensions section. Catalyst's Text would also work
// but it's defined in tests as a paragraph; keep this inline.
function Text({ children, className }: React.PropsWithChildren<{ className?: string }>) {
  return <span className={className ?? 'text-sm text-zinc-700 dark:text-zinc-300'}>{children}</span>;
}
