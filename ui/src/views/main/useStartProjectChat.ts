// Starts a project-scoped chat: creates a project_chat conversation, seeds the list
// cache, closes the main window (it's global — otherwise the new conversation would
// keep rendering the projects view), and navigates to the thread. Shared by the
// project detail header and the project list cards.

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  PROMPT_TYPE_PROJECT_CHAT,
  createAndSeedConversation,
} from '../../api/conversations';
import { useMainWindowStore } from '../../store/mainWindow';

export function useStartProjectChat() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const closeMainWindow = useMainWindowStore((s) => s.closeMainWindow);

  return useCallback(
    async (projectUuid: string) => {
      const created = await createAndSeedConversation(qc, {
        prompt_type: PROMPT_TYPE_PROJECT_CHAT,
        project_uuid: projectUuid,
      });
      closeMainWindow();
      navigate(`/c/${created.conversation_uuid}`);
    },
    [qc, navigate, closeMainWindow],
  );
}
