// Routes an /c/:conversationId URL to the chat workspace. Both project chats and position chats
// (ekt_calculator, scoped to one LV position) render in the workspace view; the calculation runs as
// part of the chat turn. Lives at the views layer because the lookup depends on async server state,
// not just the URL.

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
    // The id is gone for good (deleted, or wiped from the DB). Send the user home
    // rather than strand them on a dead URL; `replace` drops the invalid id from history.
    return <Navigate to="/" replace />;
  }

  if (
    data.prompt_type === 'project_chat' ||
    data.prompt_type === 'ekt_calculator' ||
    data.prompt_type === 'katalog_chat'
  ) {
    return <WorkspaceView />;
  }
  return (
    <EmptyState
      title="Unsupported conversation type"
      description={`prompt_type: ${data.prompt_type}`}
    />
  );
}
