// Edit a prompt's system prompt and temperature. Saving appends a new version
// (model_name and top_p carry over from the base), which becomes the active one.

import { useState } from 'react';
import type { PromptVersionRead } from '../../../types/generated';
import { useCreatePromptVersion } from '../../../api/prompts';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../../components/ui/dialog';
import { Field, Label } from '../../../components/ui/fieldset';
import { Input } from '../../../components/ui/input';
import { Textarea } from '../../../components/ui/textarea';
import { Button } from '../../../components/ui/button';

export function PromptEditDialog({
  prompt,
  open,
  onClose,
}: {
  prompt: PromptVersionRead;
  open: boolean;
  onClose: () => void;
}) {
  const create = useCreatePromptVersion();
  const [modelName, setModelName] = useState(prompt.model_name);
  const [systemPrompt, setSystemPrompt] = useState(prompt.system_prompt);
  const [temperature, setTemperature] = useState(
    prompt.temperature == null ? '' : String(prompt.temperature),
  );
  const [reasoningEffort, setReasoningEffort] = useState(prompt.reasoning_effort ?? '');
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (create.isPending) return;
    setError(null);
    onClose();
  };

  const parsedTemperature = temperature.trim() === '' ? null : Number(temperature);
  const temperatureInvalid =
    parsedTemperature !== null && Number.isNaN(parsedTemperature);
  const parsedReasoningEffort = reasoningEffort.trim() === '' ? null : reasoningEffort.trim();
  const unchanged =
    modelName === prompt.model_name &&
    systemPrompt === prompt.system_prompt &&
    parsedTemperature === (prompt.temperature ?? null) &&
    parsedReasoningEffort === (prompt.reasoning_effort ?? null);

  const submit = async () => {
    setError(null);
    try {
      await create.mutateAsync({
        prompt_type: prompt.prompt_type,
        model_name: modelName,
        system_prompt: systemPrompt,
        temperature: parsedTemperature,
        top_p: prompt.top_p,
        reasoning_effort: parsedReasoningEffort,
      });
      close();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Dialog open={open} onClose={close} size="2xl">
      <DialogTitle>
        Edit {prompt.prompt_type} (v{prompt.version})
      </DialogTitle>
      <DialogBody className="flex flex-col gap-4">
        <Field>
          <Label>Model</Label>
          <Input
            value={modelName}
            placeholder="e.g. openai/gpt-5.4-mini"
            onChange={(e) => setModelName(e.target.value)}
            className="mt-2"
          />
        </Field>
        <Field>
          <Label>System prompt</Label>
          <Textarea
            rows={16}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            className="mt-2 font-mono"
          />
        </Field>
        <Field>
          <Label>Temperature</Label>
          <Input
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={temperature}
            placeholder="none"
            onChange={(e) => setTemperature(e.target.value)}
            className="mt-2"
          />
        </Field>
        <Field>
          <Label>Reasoning effort</Label>
          <Input
            value={reasoningEffort}
            placeholder="none (e.g. low, medium, high)"
            onChange={(e) => setReasoningEffort(e.target.value)}
            className="mt-2"
          />
        </Field>
        {error && (
          <div className="text-sm text-red-600 dark:text-red-400">{error}</div>
        )}
      </DialogBody>
      <DialogActions>
        <Button plain onClick={close} disabled={create.isPending}>
          Cancel
        </Button>
        <Button
          onClick={submit}
          disabled={
            create.isPending ||
            temperatureInvalid ||
            unchanged ||
            modelName.trim() === '' ||
            systemPrompt.trim() === ''
          }
        >
          {create.isPending ? 'Saving…' : 'Save as new version'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
