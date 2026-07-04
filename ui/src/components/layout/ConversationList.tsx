// Flat list of conversations for one already-filtered group (the sidebar renders it for project
// chats). Each row navigates to the conversation; a right-aligned kebab menu offers "New" (a fresh
// chat scoped to the same project) and "Remove" (delete the conversation).

import { useParams, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { EllipsisVerticalIcon } from '@heroicons/react/20/solid';
import type { ConversationRead } from '../../types/generated';
import { formatRelativeTime } from '../../lib/format';
import { useDeleteConversation } from '../../api/conversations';
import { useStartProjectChat } from '../../views/main/useStartProjectChat';
import { useMainWindowStore } from '../../store/mainWindow';
import { useCloseTab } from './useCloseTab';
import { Dropdown, DropdownButton, DropdownItem, DropdownMenu } from '../ui/dropdown';

interface ConversationListProps {
  items: ConversationRead[];
  emptyHint?: string;
}

export function ConversationList({ items, emptyHint }: ConversationListProps) {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const deleteConversation = useDeleteConversation();
  const startProjectChat = useStartProjectChat();
  const closeMainWindow = useMainWindowStore((s) => s.closeMainWindow);
  const closeTab = useCloseTab();

  // A component window (View Prompts, View Project) covers the conversation view,
  // so it must close before the clicked conversation can render.
  const openConversation = (conversationUuid: string) => {
    closeMainWindow();
    navigate(`/c/${conversationUuid}`);
  };

  if (items.length === 0) {
    return (
      <div className="px-1 py-1 text-xs text-zinc-500 dark:text-zinc-400">
        {emptyHint ?? 'No conversations yet.'}
      </div>
    );
  }

  const onRemove = (c: ConversationRead) => {
    // Close its tab too; useCloseTab moves to the neighbour when it was active.
    deleteConversation.mutate(c.conversation_uuid, {
      onSuccess: () => closeTab(c.conversation_uuid),
    });
  };

  return (
    <div className="flex flex-col gap-0.5">
      {items.map((c) => {
        const active = c.conversation_uuid === conversationId;
        return (
          <div
            key={c.conversation_uuid}
            className={clsx(
              'flex items-center gap-1 rounded-md pr-1',
              active
                ? 'bg-zinc-200 dark:bg-zinc-700'
                : 'hover:bg-zinc-100 dark:hover:bg-zinc-800',
            )}
          >
            <button
              onClick={() => openConversation(c.conversation_uuid)}
              className={clsx(
                'flex min-w-0 flex-1 flex-col items-start gap-0.5 px-2 py-1.5 text-left text-sm',
                active
                  ? 'text-zinc-950 dark:text-white'
                  : 'text-zinc-700 dark:text-zinc-300',
              )}
            >
              <div className="line-clamp-1 w-full">{c.title ?? 'Untitled'}</div>
              <div className="text-xs text-zinc-500 dark:text-zinc-400">
                {formatRelativeTime(c.updated_at)}
              </div>
            </button>
            <Dropdown>
              <DropdownButton
                as="button"
                aria-label="Conversation actions"
                className="shrink-0 rounded p-1 text-zinc-400 transition hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-700 dark:hover:text-zinc-200"
              >
                <EllipsisVerticalIcon className="h-4 w-4" />
              </DropdownButton>
              <DropdownMenu anchor="bottom end">
                <DropdownItem
                  onClick={() => {
                    if (c.project_uuid) void startProjectChat(c.project_uuid);
                  }}
                >
                  New
                </DropdownItem>
                <DropdownItem onClick={() => onRemove(c)}>Remove</DropdownItem>
              </DropdownMenu>
            </Dropdown>
          </div>
        );
      })}
    </div>
  );
}
