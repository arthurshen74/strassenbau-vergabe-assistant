// Transient panel above the chat that walks the user through:
//   extract (pasted text) -> review/edit in <PositionForm> -> save.
//
// We render this OUTSIDE <MessageList> because the form isn't a
// MessageDTO and shouldn't be smuggled in. Showing it as a panel also
// lets the user scroll the chat history independently while the draft
// stays visible.
//
// The panel is `source`-driven. Re-mounting (i.e. a new key) restarts
// extraction; the parent owns the source and unmounts the panel on
// dismiss/save.

import { useEffect, useState } from 'react';
import {
  extractPositionFromText,
  useCreatePosition,
} from '../../../api/positions';
import { ApiError } from '../../../api/client';
import { PositionForm } from '../tools/PositionForm';
import { InlineToolResult } from '../../../components/chat/InlineToolResult';
import { ThinkingIndicator } from '../../../components/feedback/ThinkingIndicator';
import type {
  ExtractedPositionDTO,
  PositionDTO,
  PositionFieldsBody,
} from '../../../types/generated';

export type PositionDraftSource = { kind: 'text'; text: string };

type DraftStage =
  | { kind: 'extracting' }
  | { kind: 'ready'; extracted: ExtractedPositionDTO }
  | { kind: 'error'; message: string };

export interface PositionDraftPanelProps {
  source: PositionDraftSource;
  onDismiss: () => void;
  /**
   * Called with the freshly-saved PositionDTO. The view typically pushes
   * it into the chat as a synthetic ``add_position`` tool result so the
   * inline card matches what the dispatcher-driven path would render.
   */
  onCreated: (position: PositionDTO) => void;
}

function sourceLabel(source: PositionDraftSource): string {
  // Show a short preview so the user sees which paste they're working on.
  const preview = source.text.trim().slice(0, 40);
  return preview ? `pasted text: "${preview}…"` : 'pasted text';
}

export function PositionDraftPanel({
  source,
  onDismiss,
  onCreated,
}: PositionDraftPanelProps) {
  const [stage, setStage] = useState<DraftStage>({ kind: 'extracting' });
  const [serverError, setServerError] = useState<string | null>(null);
  const create = useCreatePosition();

  // Kick off extraction once per mounted source. The `cancelled` flag
  // handles React StrictMode's double-invocation correctly: the first
  // fire's cleanup sets `cancelled = true` so its result is discarded,
  // and the second fire starts a fresh extraction that runs to completion.
  // A previous `startedRef` guard was removed because it prevented the
  // second fire from running at all, leaving the panel stuck in
  // "extracting" forever.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const extracted = await extractPositionFromText(source.text);
        if (cancelled) return;
        setStage({ kind: 'ready', extracted });
      } catch (err) {
        if (cancelled) return;
        setStage({
          kind: 'error',
          message: (err as Error).message ?? 'Extraction failed',
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [source]);

  const handleSubmit = async (body: PositionFieldsBody) => {
    setServerError(null);
    try {
      const saved = await create.mutateAsync(body);
      onCreated(saved);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? formatApiError(err)
          : (err as Error).message;
      setServerError(msg);
    }
  };

  const label = sourceLabel(source);

  return (
    <div className="max-h-[55vh] overflow-y-auto border-b border-zinc-950/5 bg-zinc-50 px-6 py-4 dark:border-white/5 dark:bg-zinc-900/40">
      {stage.kind === 'extracting' && (
        // ThinkingIndicator provides its own card chrome (same border +
        // background as InlineToolResult) so we don't double-wrap it.
        <ThinkingIndicator
          label={`Extracting position from ${label}`}
          className="max-w-4xl"
        />
      )}

      {stage.kind !== 'extracting' && (
        <InlineToolResult className="max-w-4xl">
          {stage.kind === 'error' && (
            <div className="flex flex-col gap-2">
              <div className="text-sm text-red-600 dark:text-red-400">
                Couldn't extract a position from {label}: {stage.message}
              </div>
              <div className="flex justify-end">
                <button
                  onClick={onDismiss}
                  className="text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}

          {stage.kind === 'ready' && (
            <PositionForm
              extracted={stage.extracted}
              heading={`Review extracted position (${label})`}
              submitLabel="Save position"
              submitting={create.isPending}
              errorMessage={serverError}
              onSubmit={handleSubmit}
              onCancel={onDismiss}
            />
          )}
        </InlineToolResult>
      )}
    </div>
  );
}

function formatApiError(err: ApiError): string {
  const body = err.body as { detail?: unknown } | null;
  if (body && body.detail) {
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: unknown) =>
          typeof d === 'object' && d && 'msg' in d
            ? String((d as { msg: unknown }).msg)
            : String(d),
        )
        .join('; ');
    }
  }
  return err.message;
}
