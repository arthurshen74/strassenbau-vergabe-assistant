// Flat list of conversations for one already-filtered group (the sidebar
// renders it once per group). The backend returns a flat list sorted by
// updated_at; grouping by prompt_type happens in the Sidebar.

import { useParams, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import type { ConversationRead } from '../../types/generated';
import { formatRelativeTime } from '../../lib/format';

interface ConversationListProps {
  items: ConversationRead[];
  emptyHint?: string;
}

export function ConversationList({ items, emptyHint }: ConversationListProps) {
  const { conversationId } = useParams();
  const navigate = useNavigate();

  if (items.length === 0) {
    return (
      <div className="px-1 py-1 text-xs text-zinc-500 dark:text-zinc-400">
        {emptyHint ?? 'No conversations yet.'}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      {items.map((c) => {
        const active = c.conversation_uuid === conversationId;
        return (
          <button
            key={c.conversation_uuid}
            onClick={() => navigate(`/c/${c.conversation_uuid}`)}
            className={clsx(
              'flex min-w-0 flex-col items-start gap-0.5 rounded-md px-2 py-1.5 text-left text-sm',
              active
                ? 'bg-zinc-200 text-zinc-950 dark:bg-zinc-700 dark:text-white'
                : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800',
            )}
          >
            <div className="line-clamp-1 w-full">{c.title ?? 'Untitled'}</div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">
              {formatRelativeTime(c.updated_at)}
            </div>
          </button>
        );
      })}
    </div>
  );
}
