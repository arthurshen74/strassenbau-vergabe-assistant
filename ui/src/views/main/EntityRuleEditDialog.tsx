// Create/edit dialog for one entity rule. The pattern is edited as raw spaCy JSON
// (a quoted phrase string or an array of token dicts); the client rejects malformed
// JSON before submitting, and the server's spaCy validation error (a 422 detail) is
// surfaced inline when a pattern compiles here but not against spaCy.

import { useEffect, useState } from 'react';

import {
  useCreateEntityRule,
  useUpdateEntityRule,
} from '../../api/entityRules';
import { ApiError } from '../../api/client';
import type { EntityRuleRead } from '../../types/generated';
import { Button } from '../../components/ui/button';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../components/ui/dialog';
import { Field, Label } from '../../components/ui/fieldset';
import { Input } from '../../components/ui/input';
import { Switch } from '../../components/ui/switch';
import { Textarea } from '../../components/ui/textarea';

const LABELS_DATALIST_ID = 'entity-rule-labels';

function serverDetail(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: unknown } | null;
    if (body && typeof body.detail === 'string') return body.detail;
  }
  return error instanceof Error ? error.message : 'Request failed.';
}

export function EntityRuleEditDialog({
  open,
  onClose,
  rule,
  labels,
}: {
  open: boolean;
  onClose: () => void;
  // null → create a new rule; a rule → edit it.
  rule: EntityRuleRead | null;
  labels: string[];
}) {
  const [label, setLabel] = useState('');
  const [patternId, setPatternId] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [patternText, setPatternText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const create = useCreateEntityRule();
  const update = useUpdateEntityRule();
  const pending = create.isPending || update.isPending;

  // Reset the form to the target rule (or blank) each time the dialog opens.
  useEffect(() => {
    if (!open) return;
    setLabel(rule?.label ?? '');
    setPatternId(rule?.pattern_id ?? '');
    setEnabled(rule?.enabled ?? true);
    setPatternText(rule ? JSON.stringify(rule.pattern, null, 2) : '');
    setError(null);
  }, [open, rule]);

  const submit = async () => {
    setError(null);

    let pattern: unknown;
    try {
      pattern = JSON.parse(patternText);
    } catch {
      setError('Pattern is not valid JSON (quote a phrase string, or use a token array).');
      return;
    }

    const patternIdValue = patternId.trim() === '' ? null : patternId.trim();
    try {
      if (rule) {
        await update.mutateAsync({
          uuid: rule.entity_rule_uuid,
          body: {
            label,
            pattern: pattern as EntityRuleRead['pattern'],
            pattern_id: patternIdValue,
            enabled,
          },
        });
      } else {
        await create.mutateAsync({
          label,
          pattern: pattern as EntityRuleRead['pattern'],
          pattern_id: patternIdValue,
          enabled,
        });
      }
      onClose();
    } catch (err) {
      setError(serverDetail(err));
    }
  };

  return (
    <Dialog open={open} onClose={onClose} size="2xl">
      <DialogTitle>{rule ? 'Edit Rule' : 'Add Rule'}</DialogTitle>
      <DialogBody className="flex flex-col gap-4">
        <div className="flex gap-4">
          <Field className="flex-1">
            <Label>Label</Label>
            <Input
              list={LABELS_DATALIST_ID}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="BAUSTOFF"
            />
            <datalist id={LABELS_DATALIST_ID}>
              {labels.map((l) => (
                <option key={l} value={l} />
              ))}
            </datalist>
          </Field>
          <Field className="flex-1">
            <Label>Pattern ID (optional)</Label>
            <Input
              value={patternId}
              onChange={(e) => setPatternId(e.target.value)}
              placeholder="baustoff_beton"
            />
          </Field>
        </div>

        <Field>
          <Label>Pattern (JSON)</Label>
          <Textarea
            rows={8}
            className="font-mono text-xs"
            value={patternText}
            onChange={(e) => setPatternText(e.target.value)}
            placeholder='"Asphaltbeton"  or  [{"ORTH": "DIN"}, {"TEXT": {"REGEX": "^\\d+$"}}]'
          />
        </Field>

        <div className="flex items-center gap-3">
          <Switch checked={enabled} onChange={setEnabled} />
          <span className="text-sm text-zinc-700 dark:text-zinc-300">Enabled</span>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </div>
        )}
      </DialogBody>
      <DialogActions>
        <Button plain onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={pending || label.trim() === ''}>
          {rule ? 'Save' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
