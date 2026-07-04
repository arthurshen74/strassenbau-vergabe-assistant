// Close a conversation tab; when it was the active one, move to its neighbour
// (or the dispatcher home when it was the last tab). Shared by the tab strip's
// close button, the sidebar's Remove, and the /close and /remove slash commands.

import { useNavigate, useParams } from 'react-router-dom';
import { neighborTab, useTabsStore } from '../../store/tabs';

export function useCloseTab() {
  const navigate = useNavigate();
  const { conversationId } = useParams();
  return (cid: string) => {
    const { openTabs, closeTab } = useTabsStore.getState();
    const neighbor = neighborTab(openTabs, cid);
    closeTab(cid);
    if (cid === conversationId) navigate(neighbor ? `/c/${neighbor}` : '/');
  };
}
