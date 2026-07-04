// Keeps one workspace panel mounted per open tab so switching tabs preserves
// live SSE streams, interrupt-form edits, and message-list scroll. Inactive
// panels stay laid out but invisible (visibility, not display:none — a
// display:none subtree loses its scroll offsets); AppShell's overlay layer
// covers the stack while the main window or a non-conversation route shows.

import { Navigate, useParams } from 'react-router-dom';
import clsx from 'clsx';
import { useConversationList } from '../../api/conversations';
import { useTabsStore } from '../../store/tabs';
import { WorkspacePanel } from '../../views/workspace/WorkspacePanel';

export function TabHost() {
  const { conversationId } = useParams();
  const openTabs = useTabsStore((s) => s.openTabs);
  const list = useConversationList();

  // Render the URL's conversation even before TabStrip's sync effect lands it
  // in the store, so a fresh navigation paints without a blank frame.
  const panelIds =
    conversationId && !openTabs.includes(conversationId) ?
      [...openTabs, conversationId]
    : openTabs;

  // The active id is gone for good (deleted, or wiped from the DB): send the
  // user home rather than strand them on a dead URL. Inactive dead tabs are
  // pruned by TabStrip instead — they must not hijack navigation.
  const notFound =
    !!conversationId &&
    !!list.data &&
    !list.isFetching &&
    !list.data.some((c) => c.conversation_uuid === conversationId);

  return (
    <>
      {notFound && (
        <Navigate
          to="/"
          replace
        />
      )}
      {panelIds.map((cid) => (
        <div
          key={cid}
          aria-hidden={cid !== conversationId}
          className={clsx(
            'absolute inset-0 flex flex-col overflow-y-auto',
            cid === conversationId ? 'visible' : 'invisible',
          )}
        >
          <WorkspacePanel conversationId={cid} />
        </div>
      ))}
    </>
  );
}
