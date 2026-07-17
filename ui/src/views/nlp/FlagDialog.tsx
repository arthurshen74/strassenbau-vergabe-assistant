// Flag capture dialog: the user records a misprediction (wrong label / not an
// entity / missed entity) with a comment; submitting persists the flag and runs
// the one-shot LLM analysis server-side. The dialog then shows the analysis
// result (category + prose) inline, or a note that analysis failed and is retriable.

import { useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { useCreateNerFlag, type NerFlagKind } from '../../api/nerFlags';
import type { NerFlag, NewNerFlag } from '../../types/generated';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../components/ui/dialog';
import { Field, Label } from '../../components/ui/fieldset';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { categoryLabel, KIND_LABELS } from './nerCategories';
import type { FlagContext, FlagTarget } from './flagTypes';

const LABEL_OPTIONS_ID = 'flag-label-options';

function serverDetail(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: unknown } | null;
    if (body && typeof body.detail === 'string') return body.detail;
  }
  return error instanceof Error ? error.message : 'Request failed.';
}

export function FlagDialog({
  open,
  onClose,
  target,
  context,
  labelOptions,
  onFlagged,
}: {
  open: boolean;
  onClose: () => void;
  target: FlagTarget | null;
  context: FlagContext;
  labelOptions: string[];
  onFlagged?: () => void;
}) {
  const [kind, setKind] = useState<NerFlagKind>('wrong_label');
  const [expectedLabel, setExpectedLabel] = useState('');
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NerFlag | null>(null);

  const create = useCreateNerFlag();

  useEffect(() => {
    if (!open || !target) return;
    setKind(target.allowedKinds[0]);
    setExpectedLabel('');
    setComment('');
    setError(null);
    setResult(null);
  }, [open, target]);

  if (!target) return null;

  const isMissed = kind === 'missed_entity';
  const needsExpected = kind === 'wrong_label' || kind === 'missed_entity';

  const submit = async () => {
    setError(null);
    const expected = expectedLabel.trim();
    const label = isMissed ? expected : target.label;
    const payload: NewNerFlag = {
      kind,
      span_text: target.spanText,
      span_start: target.spanStart,
      span_end: target.spanEnd,
      sentence_text: target.sentenceText,
      label,
      expected_label:
        kind === 'wrong_label' ? expected || null : isMissed ? expected : null,
      user_comment: comment.trim(),
      source_text: context.sourceText,
      entity_snapshot: context.entitySnapshot,
      lv_item_uuid: context.lvItemUuid,
      document_uuid: context.documentUuid,
    };
    try {
      const flag = await create.mutateAsync(payload);
      setResult(flag);
      onFlagged?.();
    } catch (err) {
      setError(serverDetail(err));
    }
  };

  const submitDisabled =
    create.isPending ||
    comment.trim() === '' ||
    (isMissed && expectedLabel.trim() === '');

  return (
    <Dialog open={open} onClose={onClose} size="xl">
      <DialogTitle>Flag misprediction</DialogTitle>
      <DialogBody className="flex flex-col gap-4">
        <div className="rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-700">
          <div className="mb-1">
            <span className="font-mono text-zinc-900 dark:text-zinc-100">
              {target.spanText}
            </span>
            {target.label && (
              <>
                {' '}
                <Badge color="amber">{target.label}</Badge>
              </>
            )}
          </div>
          <div className="text-xs text-zinc-500">{target.sentenceText}</div>
        </div>

        {result ? (
          <AnalysisResult flag={result} />
        ) : (
          <>
            {target.allowedKinds.length > 1 && (
              <Field>
                <Label>Problem</Label>
                <div className="flex gap-2">
                  {target.allowedKinds.map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setKind(k)}
                      className={`rounded-md border px-3 py-1.5 text-sm transition ${
                        kind === k
                          ? 'border-blue-600 bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                          : 'border-zinc-200 text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800'
                      }`}
                    >
                      {KIND_LABELS[k]}
                    </button>
                  ))}
                </div>
              </Field>
            )}

            {needsExpected && (
              <Field>
                <Label>
                  {isMissed ? 'Expected label' : 'Expected label (optional)'}
                </Label>
                <Input
                  list={LABEL_OPTIONS_ID}
                  value={expectedLabel}
                  onChange={(e) => setExpectedLabel(e.target.value)}
                  placeholder="BAUSTOFF"
                />
                <datalist id={LABEL_OPTIONS_ID}>
                  {labelOptions.map((l) => (
                    <option key={l} value={l} />
                  ))}
                </datalist>
              </Field>
            )}

            <Field>
              <Label>Comment</Label>
              <Textarea
                rows={3}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="What is wrong and why?"
              />
            </Field>

            {error && (
              <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-400">
                {error}
              </div>
            )}
          </>
        )}
      </DialogBody>
      <DialogActions>
        {result ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button plain onClick={onClose} disabled={create.isPending}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={submitDisabled}>
              {create.isPending ? 'Analyzing…' : 'Flag & analyze'}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}

function AnalysisResult({ flag }: { flag: NerFlag }) {
  const category = flag.category_override ?? flag.category ?? null;
  if (category === null) {
    return (
      <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
        Flag saved, but the analysis did not complete. Retry it from the NER
        Analysis page.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-md border border-zinc-200 p-3 dark:border-zinc-700">
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500">Category</span>
        <Badge color={category === 'ambiguity' ? 'red' : 'blue'}>
          {categoryLabel(category)}
        </Badge>
      </div>
      {flag.llm_analysis && (
        <p className="text-sm text-zinc-700 dark:text-zinc-300">{flag.llm_analysis}</p>
      )}
    </div>
  );
}
