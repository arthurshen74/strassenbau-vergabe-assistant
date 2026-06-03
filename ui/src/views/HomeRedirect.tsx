// Lands at "/". If the user has any prior conversation, jump to the most recent. Otherwise show an
// empty state: conversations are project chats, started by opening a project from the sidebar.

import { Navigate } from 'react-router-dom';
import { useConversationList } from '../api/conversations';
import { LoadingState } from '../components/feedback/LoadingState';
import { EmptyState } from '../components/feedback/EmptyState';

export function HomeRedirect() {
  const { data, isLoading } = useConversationList();

  if (isLoading) return <LoadingState />;
  const items = data ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title="No conversations yet"
        description='Open "View Project" in the sidebar, choose a project, and start a chat to ask about its documents.'
      />
    );
  }
  // Sidebar list is already sorted by updated_at descending (server-side).
  return <Navigate to={`/c/${items[0].conversation_uuid}`} replace />;
}
