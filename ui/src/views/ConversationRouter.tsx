// Routes an /c/:conversationId URL to the right view based on the
// conversation's `prompt_type`. Both dispatcher and project-chat conversations
// run the same streaming loop (the backend selects tools by prompt_type), so
// both render WorkspaceView. Lives at the views layer because the dispatch
// depends on async server state, not just the URL.

import { Navigate, useParams } from 'react-router-dom';
import { useConversation } from '../api/conversations';
import { WorkspaceView } from './workspace/WorkspaceView';
import { LoadingState } from '../components/feedback/LoadingState';
import { ErrorState } from '../components/feedback/ErrorState';
import { EmptyState } from '../components/feedback/EmptyState';

export function ConversationRouter() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const { data, isLoading, isFetching, isError, error, refetch } =
    useConversation(conversationId);

  if (!conversationId) {
    return <ErrorState message="Missing conversation id" />;
  }
  if (isLoading) return <LoadingState />;
  if (isError) {
    return (
      <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
    );
  }
  if (!data) {
    // List loaded but this id isn't in it yet (e.g. a fresh create still
    // settling) — keep showing a spinner while a refetch is in flight.
    if (isFetching) return <LoadingState />;
    // The id is gone for good (deleted, or wiped from the DB). Rather than
    // strand the user on a dead URL, start a fresh thread. `replace` drops the
    // invalid id from history so back/refresh don't bounce back to it.
    return <Navigate to="/c/new" replace />;
  }

  switch (data.prompt_type) {
    case 'dispatcher':
    case 'project_chat':
      return <WorkspaceView />;
    default:
      return (
        <EmptyState
          title="Unsupported conversation type"
          description={`prompt_type: ${data.prompt_type}`}
        />
      );
  }
}
