// Starts a Katalog-Chat: creates a katalog_chat conversation (global — the catalog is not
// project-scoped, so no project_uuid), seeds the list cache, closes the main window, and navigates
// to the thread. Mirrors useStartProjectChat; the catalog agent answers read-only questions about
// the persisted Kalkulationskatalog.

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  PROMPT_TYPE_KATALOG_CHAT,
  createAndSeedConversation,
} from '../../api/conversations';
import { useMainWindowStore } from '../../store/mainWindow';

export function useStartKatalogChat() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const closeMainWindow = useMainWindowStore((s) => s.closeMainWindow);

  return useCallback(async () => {
    const created = await createAndSeedConversation(qc, {
      prompt_type: PROMPT_TYPE_KATALOG_CHAT,
      title: 'Katalog-Chat',
    });
    closeMainWindow();
    navigate(`/c/${created.conversation_uuid}`);
  }, [qc, navigate, closeMainWindow]);
}
