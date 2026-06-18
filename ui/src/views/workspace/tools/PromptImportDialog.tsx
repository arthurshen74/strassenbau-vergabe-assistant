// Import a `.prompt` file (select or drag-and-drop). The file's frontmatter and
// body are parsed into a new prompt version; the prompt_type comes from the
// filename stem. Saving appends a new version, which becomes the active one.

import { useRef, useState } from 'react';
import type { DragEvent } from 'react';
import type { PromptVersionCreate } from '../../../types/generated';
import { useCreatePromptVersion } from '../../../api/prompts';
import {
  PROMPT_FILE_SUFFIX,
  PromptFileError,
  parsePromptFile,
} from './promptFile';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../../components/ui/dialog';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { Text } from '../../../components/ui/text';

export function PromptImportDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const create = useCreatePromptVersion();
  const inputRef = useRef<HTMLInputElement>(null);
  const [parsed, setParsed] = useState<PromptVersionCreate | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (create.isPending) return;
    setParsed(null);
    setFilename(null);
    setDragging(false);
    setError(null);
    onClose();
  };

  const ingest = async (file: File) => {
    setError(null);
    setParsed(null);
    setFilename(file.name);
    try {
      setParsed(parsePromptFile(file.name, await file.text()));
    } catch (err) {
      if (err instanceof PromptFileError) setError(err.message);
      else setError(err instanceof Error ? err.message : String(err));
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) void ingest(file);
  };

  const submit = async () => {
    if (!parsed) return;
    setError(null);
    try {
      await create.mutateAsync(parsed);
      close();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Dialog open={open} onClose={close} size="2xl">
      <DialogTitle>Import .prompt file</DialogTitle>
      <DialogBody className="flex flex-col gap-4">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed p-8 text-center text-sm transition-colors ${
            dragging
              ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30'
              : 'border-zinc-950/15 hover:border-zinc-950/30 dark:border-white/15 dark:hover:border-white/30'
          }`}
        >
          <Text>
            Drop a <span className="font-mono">{PROMPT_FILE_SUFFIX}</span> file here, or click to
            select
          </Text>
          {filename && (
            <Text className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
              {filename}
            </Text>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={PROMPT_FILE_SUFFIX}
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void ingest(file);
              e.target.value = '';
            }}
          />
        </div>

        {parsed && (
          <div className="flex flex-col gap-2 rounded-md border border-zinc-950/5 p-3 dark:border-white/10">
            <div className="flex flex-wrap items-center gap-2">
              <Badge color="purple">{parsed.prompt_type}</Badge>
              <Text className="text-xs">{parsed.model_name}</Text>
            </div>
            <div className="flex flex-wrap gap-2 text-xs text-zinc-500 dark:text-zinc-400">
              {parsed.temperature != null && <span>temp {parsed.temperature}</span>}
              {parsed.top_p != null && <span>top_p {parsed.top_p}</span>}
              {parsed.reasoning_effort != null && (
                <span>effort {parsed.reasoning_effort}</span>
              )}
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-2 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
              {parsed.system_prompt}
            </pre>
          </div>
        )}

        {error && (
          <div className="text-sm text-red-600 dark:text-red-400">{error}</div>
        )}
      </DialogBody>
      <DialogActions>
        <Button plain onClick={close} disabled={create.isPending}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!parsed || create.isPending}>
          {create.isPending ? 'Saving…' : 'Save as new version'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
