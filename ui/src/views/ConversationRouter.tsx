// Routes an /c/:conversationId URL to the right view based on the
// conversation's `type`. Lives at the views layer (not in App.tsx)
// because the dispatch decision depends on async server state, not
// just the URL.
//
// PrepSession and JudgeRun views aren't built yet; we render a small
// placeholder for those types so navigation still works.

import { useParams } from 'react-router-dom';
import { useConversation } from '../api/conversations';
import { WorkspaceView } from './workspace/WorkspaceView';
import { PrepSessionView } from './prep_session/PrepSessionView';
import { LoadingState } from '../components/feedback/LoadingState';
import { ErrorState } from '../components/feedback/ErrorState';
import { EmptyState } from '../components/feedback/EmptyState';

export function ConversationRouter() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const { data, isLoading, isError, error, refetch } = useConversation(conversationId);

  if (!conversationId) {
    return <ErrorState message="Missing conversation id" />;
  }
  if (isLoading) return <LoadingState />;
  if (isError) {
    return (
      <ErrorState
        message={(error as Error).message}
        onRetry={() => refetch()}
      />
    );
  }
  if (!data) return <EmptyState title="Conversation not found" />;

  switch (data.type) {
    case 'workspace':
      return <WorkspaceView />;
    case 'prep_session':
      return <PrepSessionView />;
    case 'judge_run':
      return (
        <EmptyState
          title="Judge run"
          description="The judge run view is not built yet."
        />
      );
    default: {
      const _exhaustive: never = data;
      void _exhaustive;
      return <EmptyState title="Unknown conversation type" />;
    }
  }
}
