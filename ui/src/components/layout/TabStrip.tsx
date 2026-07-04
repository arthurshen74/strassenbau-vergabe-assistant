// Horizontal strip of open conversation tabs, mounted in the shell above the
// routed content (and above the main-window overlay, so switching tabs always
// works). The URL stays the source of truth for the active tab: navigating to
// /c/:id opens its tab here via the sync effect, and clicking a tab navigates.

import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import clsx from 'clsx';
import {
  BookOpenIcon,
  CalculatorIcon,
  ChatBubbleLeftIcon,
  PauseCircleIcon,
  XMarkIcon,
} from '@heroicons/react/20/solid';
import {
  PROMPT_TYPE_EKT_CALCULATOR,
  PROMPT_TYPE_KATALOG_CHAT,
  useConversationList,
} from '../../api/conversations';
import { useTabsStore } from '../../store/tabs';
import { useUIStore } from '../../store/ui';
import { useMainWindowStore } from '../../store/mainWindow';
import { useCloseTab } from './useCloseTab';
import type { ConversationRead } from '../../types/generated';

function tabIcon(promptType: string | undefined) {
  if (promptType === PROMPT_TYPE_EKT_CALCULATOR) return CalculatorIcon;
  if (promptType === PROMPT_TYPE_KATALOG_CHAT) return BookOpenIcon;
  return ChatBubbleLeftIcon;
}

function tabTitle(c: ConversationRead | undefined): string {
  if (!c) return '…';
  if (c.title) return c.title;
  if (c.prompt_type === PROMPT_TYPE_EKT_CALCULATOR) return 'EKT-Position';
  if (c.prompt_type === PROMPT_TYPE_KATALOG_CHAT) return 'Katalog-Chat';
  return 'Untitled';
}

export function TabStrip() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const openTabs = useTabsStore((s) => s.openTabs);
  const openTab = useTabsStore((s) => s.openTab);
  const pruneTabs = useTabsStore((s) => s.pruneTabs);
  const activeStreamIds = useUIStore((s) => s.activeStreamIds);
  const closeMainWindow = useMainWindowStore((s) => s.closeMainWindow);
  const closeTab = useCloseTab();
  const listData = useConversationList().data;

  // URL -> store: any navigation to a conversation opens its tab.
  useEffect(() => {
    if (conversationId) openTab(conversationId);
  }, [conversationId, openTab]);

  // Drop tabs for conversations that no longer exist (deleted, other session).
  useEffect(() => {
    if (listData) pruneTabs(listData.map((c) => c.conversation_uuid));
  }, [listData, pruneTabs]);

  if (openTabs.length === 0) return null;

  const byId = new Map((listData ?? []).map((c) => [c.conversation_uuid, c]));

  return (
    <div
      role="tablist"
      aria-label="Open conversations"
      className="flex h-9 shrink-0 items-end gap-1 overflow-x-auto border-b border-zinc-950/5 bg-zinc-50 px-2 dark:border-white/5 dark:bg-zinc-900"
    >
      {openTabs.map((cid) => {
        const c = byId.get(cid);
        const active = cid === conversationId;
        const streaming = !!activeStreamIds[cid];
        const paused = c?.calculation_status === 'awaiting_input';
        const Icon = tabIcon(c?.prompt_type);
        return (
          <div
            key={cid}
            role="tab"
            aria-selected={active}
            className={clsx(
              'group flex max-w-48 shrink-0 items-center gap-1 rounded-t-md border border-b-0 py-1 pr-1 pl-2.5 text-xs',
              active
                ? 'border-zinc-950/10 bg-white text-zinc-900 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-100'
                : 'border-transparent text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200',
            )}
          >
            <button
              onClick={() => {
                closeMainWindow();
                navigate(`/c/${cid}`);
              }}
              className="flex min-w-0 items-center gap-1.5"
            >
              {streaming ?
                <span
                  className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-emerald-500"
                  aria-label="Streaming"
                />
              : <Icon className="h-3.5 w-3.5 shrink-0 opacity-60" />}
              <span className="truncate">{tabTitle(c)}</span>
              {paused && (
                <PauseCircleIcon
                  className="h-3.5 w-3.5 shrink-0 text-amber-500"
                  aria-label="Awaiting review"
                />
              )}
            </button>
            <button
              onClick={() => closeTab(cid)}
              aria-label="Close tab"
              className={clsx(
                'shrink-0 rounded p-0.5 text-zinc-400 transition hover:bg-zinc-200 hover:text-zinc-700 focus-visible:opacity-100 dark:hover:bg-zinc-700 dark:hover:text-zinc-200',
                active ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
              )}
            >
              <XMarkIcon className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
