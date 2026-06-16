// Starts an EKT calculator run for an LV position: creates the ekt_calculator conversation, seeds
// the conversation-list cache so it resolves immediately, closes the (global) main window overlay
// so the new conversation is visible underneath, then navigates to it. Tracks the OZ of the
// in-flight run so callers can disable the trigger. Shared by the LV positions table and the
// inline chat result cards (which only have a project_uuid for some tool results).

import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { createCalculation } from '../../api/calculations';
import { conversationKeys } from '../../api/conversations';
import { useMainWindowStore } from '../../store/mainWindow';
import type { ConversationRead } from '../../types/generated';

export function useRunCalculation(projectUuid: string | undefined) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const closeMainWindow = useMainWindowStore((s) => s.closeMainWindow);
  const [starting, setStarting] = useState<string | null>(null);

  const runCalculation = useCallback(
    async (oz: string) => {
      if (!projectUuid) return;
      setStarting(oz);
      try {
        const convo = await createCalculation(projectUuid, oz);
        qc.setQueryData<ConversationRead[]>(conversationKeys.list(), (old) =>
          old ? [convo, ...old] : [convo],
        );
        qc.invalidateQueries({ queryKey: conversationKeys.all });
        closeMainWindow();
        navigate(`/c/${convo.conversation_uuid}`);
      } finally {
        setStarting(null);
      }
    },
    [projectUuid, qc, navigate, closeMainWindow],
  );

  return { runCalculation, starting };
}
