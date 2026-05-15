// Lands at "/". If the user has any prior conversation, jump to the most
// recent. Otherwise show the empty state encouraging them to start a new
// thread. Keeps the root URL meaningful without hard-coding /c/new.

import { Navigate } from 'react-router-dom';
import { useConversationList } from '../api/conversations';
import { LoadingState } from '../components/feedback/LoadingState';
import { EmptyState } from '../components/feedback/EmptyState';
import { Button } from '../components/ui/button';
import { useNavigate } from 'react-router-dom';

export function HomeRedirect() {
  const { data, isLoading } = useConversationList();
  const navigate = useNavigate();

  if (isLoading) return <LoadingState />;
  const items = data ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title="No conversations yet"
        description="Start a new thread to chat with the dispatcher."
        action={
          <Button onClick={() => navigate('/c/new')}>New thread</Button>
        }
      />
    );
  }
  // Sidebar list is already sorted by updated_at descending (server-side).
  return <Navigate to={`/c/${items[0].id}`} replace />;
}
