// The neutral dispatcher home at "/". Conversations are project chats, reachable from the sidebar
// list; new ones start from a project (sidebar "View Project"). The single-shot dispatcher command
// bar lives here, under the heading. We intentionally do NOT auto-open a conversation, so "/" is a
// real place to return to when leaving a project chat.

import { EmptyState } from '../components/feedback/EmptyState';
import { DispatchBar } from '../components/layout/DispatchBar';

export function Home() {
  return (
    <EmptyState
      title="Roadbuilders Assistant"
      description="Ask the assistant below, open “View Project” to start a project chat, or pick a project conversation from the list."
      action={
        <div className="w-80 max-w-full">
          <DispatchBar />
        </div>
      }
    />
  );
}
