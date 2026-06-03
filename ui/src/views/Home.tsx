// The neutral dispatcher home at "/". Conversations are project chats, reachable from the sidebar
// list; new ones start from a project (sidebar "View Project"). The command bar in the sidebar
// routes everything else. We intentionally do NOT auto-open a conversation, so "/" is a real place
// to return to when leaving a project chat.

import { EmptyState } from '../components/feedback/EmptyState';

export function Home() {
  return (
    <EmptyState
      title="Roadbuilders Assistant"
      description="Use the command bar in the sidebar, open “View Project” to start a project chat, or pick a project conversation from the list."
    />
  );
}
