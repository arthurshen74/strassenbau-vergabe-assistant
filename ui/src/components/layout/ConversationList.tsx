// Sidebar list of recent conversations. Groups by type so the user can
// scan workspace threads vs. ongoing prep sessions vs. judge runs.
//
// Keeping grouping logic here (rather than in a global selector) because
// it's purely a presentation choice for THIS surface — the API returns
// a flat list sorted by updated_at.
//
// Per-row actions (currently: delete) only render for workspace threads.
// Prep sessions and judge runs have their own lifecycles and can't be
// torn down from here — see ARCHITECTURE.md §4.

import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { EllipsisHorizontalIcon } from '@heroicons/react/16/solid';
import type { ConversationSummaryDTO } from '../../types/generated';
import { formatRelativeTime } from '../../lib/format';
import { useDeleteConversation, useRenameConversation } from '../../api/conversations';
import { useDeletePrepSession } from '../../api/sessions';
import {
  Dropdown,
  DropdownButton,
  DropdownItem,
  DropdownMenu,
} from '../ui/dropdown';
import {
  Alert,
  AlertActions,
  AlertDescription,
  AlertTitle,
} from '../ui/alert';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Button } from '../ui/button';

interface ConversationListProps {
  items: ConversationSummaryDTO[];
}

const TYPE_LABELS: Record<ConversationSummaryDTO['type'], string> = {
  workspace: 'Workspace',
  prep_session: 'Prep sessions',
  judge_run: 'Judge runs',
};

const TYPE_ORDER: ConversationSummaryDTO['type'][] = [
  'workspace',
  'prep_session',
  'judge_run',
];

export function ConversationList({ items }: ConversationListProps) {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const deleteConversationMutation = useDeleteConversation();
  const deleteSessionMutation = useDeletePrepSession();
  const renameMutation = useRenameConversation();

  // Pending deletion target. Storing the whole summary (not just the id)
  // so the confirmation dialog can show the thread title without needing
  // a second lookup.
  const [pendingDelete, setPendingDelete] =
    useState<ConversationSummaryDTO | null>(null);

  // Pending rename target + draft title.
  const [pendingRename, setPendingRename] =
    useState<ConversationSummaryDTO | null>(null);
  const [renameTitle, setRenameTitle] = useState('');
  const renameInputRef = useRef<HTMLInputElement>(null);

  const deleteMutation =
    pendingDelete?.type === 'prep_session'
      ? deleteSessionMutation
      : deleteConversationMutation;

  // Auto-select the text in the rename input when the dialog opens so the
  // user can start typing immediately without manually clearing the field.
  useEffect(() => {
    if (pendingRename) {
      // Give the dialog time to mount before focusing.
      requestAnimationFrame(() => renameInputRef.current?.select());
    }
  }, [pendingRename]);

  const openRename = (c: ConversationSummaryDTO) => {
    setRenameTitle(c.title);
    setPendingRename(c);
  };

  const confirmRename = async () => {
    if (!pendingRename) return;
    const trimmed = renameTitle.trim();
    if (!trimmed) return;
    try {
      await renameMutation.mutateAsync({ id: pendingRename.id, title: trimmed });
      setPendingRename(null);
    } catch {
      // Leave the dialog open so the user can retry.
    }
  };

  const groups = TYPE_ORDER.map((t) => ({
    type: t,
    label: TYPE_LABELS[t],
    items: items.filter((i) => i.type === t),
  })).filter((g) => g.items.length > 0);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const wasActive = pendingDelete.id === conversationId;
    try {
      await deleteMutation.mutateAsync(pendingDelete.id);
      setPendingDelete(null);
      if (wasActive) {
        // Bounce to the home redirect, which will pick the next thread
        // (or land on the new-thread view if none remain).
        navigate('/');
      }
    } catch {
      // Leave the dialog open so the user can retry; the mutation's
      // error state would show in the button label if we wired it up,
      // but for now we just don't auto-close on failure.
    }
  };

  if (items.length === 0) {
    return (
      <div className="px-1 py-2 text-xs text-zinc-500 dark:text-zinc-400">
        No conversations yet. Start a new thread to begin.
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-col gap-4">
        {groups.map((g) => (
          <div key={g.type} className="flex flex-col gap-1">
            <div className="px-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              {g.label}
            </div>
            {g.items.map((c) => {
              const active = c.id === conversationId;
              const canDelete =
                c.type === 'workspace' || c.type === 'prep_session';
              const canRename = c.type === 'workspace';
              return (
                <div
                  key={c.id}
                  className={clsx(
                    'group relative flex items-stretch rounded-md',
                    active
                      ? 'bg-zinc-200 text-zinc-950 dark:bg-zinc-700 dark:text-white'
                      : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800',
                  )}
                >
                  <button
                    onClick={() => navigate(`/c/${c.id}`)}
                    className="flex min-w-0 flex-1 flex-col items-start gap-0.5 px-2 py-1.5 text-left text-sm"
                  >
                    <div className="line-clamp-1 w-full">{c.title}</div>
                    <div className="flex w-full items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
                      <span>{formatRelativeTime(c.updated_at)}</span>
                      {c.status && (
                        <span className="rounded bg-zinc-100 px-1 py-px dark:bg-zinc-800">
                          {c.status}
                        </span>
                      )}
                    </div>
                  </button>
                  {(canDelete || canRename) && (
                    <Dropdown>
                      <DropdownButton
                        plain
                        aria-label="Thread actions"
                        // Hidden until row hover / focus / open, so the
                        // sidebar stays calm at rest. The active row
                        // shows it always so actions on the current thread
                        // are one click away.
                        className={clsx(
                          '!mr-1 !px-1.5 self-center opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100 data-[open]:opacity-100',
                          active && 'opacity-100',
                        )}
                      >
                        <EllipsisHorizontalIcon />
                      </DropdownButton>
                      <DropdownMenu anchor="bottom end">
                        {canRename && (
                          <DropdownItem onClick={() => openRename(c)}>
                            Rename
                          </DropdownItem>
                        )}
                        {canDelete && (
                          <DropdownItem
                            onClick={() => setPendingDelete(c)}
                            className="!text-red-600 dark:!text-red-400"
                          >
                            {c.type === 'prep_session'
                              ? 'Delete session'
                              : 'Delete thread'}
                          </DropdownItem>
                        )}
                      </DropdownMenu>
                    </Dropdown>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <Dialog
        open={pendingRename !== null}
        onClose={() => {
          if (!renameMutation.isPending) setPendingRename(null);
        }}
        size="sm"
      >
        <DialogTitle>Rename thread</DialogTitle>
        <DialogBody>
          <Input
            ref={renameInputRef}
            type="text"
            value={renameTitle}
            onChange={(e) => setRenameTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') confirmRename();
              if (e.key === 'Escape') setPendingRename(null);
            }}
            disabled={renameMutation.isPending}
            autoFocus
          />
        </DialogBody>
        <DialogActions>
          <Button
            plain
            onClick={() => setPendingRename(null)}
            disabled={renameMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={confirmRename}
            disabled={renameMutation.isPending || !renameTitle.trim()}
          >
            {renameMutation.isPending ? 'Saving…' : 'Rename'}
          </Button>
        </DialogActions>
      </Dialog>

      <Alert
        open={pendingDelete !== null}
        onClose={() => {
          if (!deleteMutation.isPending) setPendingDelete(null);
        }}
      >
        <AlertTitle>
          {pendingDelete?.type === 'prep_session'
            ? 'Delete this session?'
            : 'Delete this thread?'}
        </AlertTitle>
        <AlertDescription>
          {pendingDelete?.type === 'prep_session' ? (
            <>
              &ldquo;{pendingDelete.title}&rdquo; will be removed from the
              sidebar. Its transcript and scores are retained internally so
              any judge runs referencing it still work.
              {pendingDelete.status === 'in_progress' && (
                <> This session is currently <strong>in progress</strong> — deleting it will end it.</>  
              )}
            </>
          ) : pendingDelete ? (
            <>
              &ldquo;{pendingDelete.title}&rdquo; and all of its messages will
              be permanently deleted. This cannot be undone.
            </>
          ) : null}
        </AlertDescription>
        <AlertActions>
          <Button
            plain
            onClick={() => setPendingDelete(null)}
            disabled={deleteMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            color="red"
            onClick={confirmDelete}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
          </Button>
        </AlertActions>
      </Alert>
    </>
  );
}
