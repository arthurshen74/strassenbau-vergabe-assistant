// Session header bar.
// Left:  position title + company, "question N of ~M · session locked" subtitle.
// Right: "Live evaluation" drawer trigger, then /exit button (with confirm dialog).

import { useState } from 'react';
import { ChartBarIcon } from '@heroicons/react/20/solid';
import { Button } from '../../components/ui/button';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
} from '../../components/ui/dialog';
import type { PrepSessionConversationDTO } from '../../types/generated';

interface SessionHeaderProps {
  session: PrepSessionConversationDTO;
  onExit: () => void;
  onBack: () => void;
  onOpenEval: () => void;
  isStreaming: boolean;
}

export function SessionHeader({
  session,
  onExit,
  onBack,
  onOpenEval,
  isStreaming,
}: SessionHeaderProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  const [company, positionTitle] = session.title.includes('::')
    ? session.title.split('::', 2)
    : [null, session.title];

  const isLocked = session.status !== 'in_progress';

  return (
    <>
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-950/5 px-4 dark:border-white/5">
        {/* Left — position info */}
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {company && (
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                {company}
              </span>
            )}
            <span className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {positionTitle}
            </span>
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            question {session.question_count} of ~{session.target_question_count}
            {' · '}
            {isLocked ? `session ${session.status}` : 'session locked'}
          </p>
        </div>

        {/* Right — actions */}
        <div className="flex shrink-0 items-center gap-2">
          <Button
            plain
            onClick={onOpenEval}
            className="flex items-center gap-1.5 text-sm"
          >
            <ChartBarIcon className="h-4 w-4" />
            Live evaluation
          </Button>

          {isLocked ? (
            // Session is already complete — no destructive action needed.
            <Button outline onClick={onBack}>
              Back
            </Button>
          ) : (
            <Button
              outline
              onClick={() => setConfirmOpen(true)}
              disabled={isStreaming}
            >
              Exit
            </Button>
          )}
        </div>
      </header>

      {/* Exit confirmation dialog */}
      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>Cancel this session?</DialogTitle>
        <DialogDescription>
          The session will be cancelled and cannot be continued. Your answers
          so far are already saved.
        </DialogDescription>
        <DialogBody />
        <DialogActions>
          <Button plain onClick={() => setConfirmOpen(false)}>
            Keep going
          </Button>
          <Button
            color="red"
            onClick={() => {
              setConfirmOpen(false);
              onExit();
            }}
          >
            Cancel session
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
