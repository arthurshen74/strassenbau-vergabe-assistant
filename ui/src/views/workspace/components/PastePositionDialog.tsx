// Modal that collects pasted job-description text and hands it back as
// a `PositionDraftSource` of kind 'text'. We use a modal here (not an
// inline expanding panel) because the expected interaction is "paste a
// chunk, click Extract" — short-lived and modal-y.
//
// The 60_000-char ceiling matches the backend's request validation;
// we surface it client-side so a paste that's way too big fails fast
// without a 422 round-trip.
//
// We keep this dialog dumb: it doesn't run extraction itself. The
// parent view decides what to do with the text (today: open a
// PositionDraftPanel with kind:'text').

import { useState } from 'react';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Textarea } from '../../../components/ui/textarea';

const MAX_PASTE_CHARS = 60_000;

export interface PastePositionDialogProps {
  open: boolean;
  onClose: () => void;
  onExtract: (text: string) => void;
}

export function PastePositionDialog({
  open,
  onClose,
  onExtract,
}: PastePositionDialogProps) {
  const [text, setText] = useState('');
  const trimmed = text.trim();
  const tooLong = text.length > MAX_PASTE_CHARS;
  const submittable = trimmed.length > 0 && !tooLong;

  const handleSubmit = () => {
    if (!submittable) return;
    onExtract(trimmed);
    setText('');
  };

  const handleClose = () => {
    setText('');
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} size="2xl">
      <DialogTitle>Paste a job description</DialogTitle>
      <DialogDescription>
        Copy the full job description here. We'll extract the title,
        company, level, salary, skills, and a summary into a form you
        can review before saving.
      </DialogDescription>
      <DialogBody>
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste the job description here…"
          rows={14}
          autoFocus
        />
        <div className="mt-2 flex items-center justify-between text-xs text-zinc-500">
          <span>
            {text.length.toLocaleString()} / {MAX_PASTE_CHARS.toLocaleString()} chars
          </span>
          {tooLong && (
            <span className="text-red-600 dark:text-red-400">
              Too long — trim or split before extracting.
            </span>
          )}
        </div>
      </DialogBody>
      <DialogActions>
        <Button plain onClick={handleClose}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={!submittable}>
          Extract
        </Button>
      </DialogActions>
    </Dialog>
  );
}
