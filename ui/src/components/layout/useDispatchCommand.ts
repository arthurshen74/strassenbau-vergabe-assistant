// Single-shot dispatcher command: POST /dispatch and, on a routable tool result, open the matching
// main window. No conversation is created and nothing is persisted — the dispatcher is stateless.

import { useCallback, useState } from 'react';
import { postStream } from '../../api/sse';
import { useMainWindowStore, viewKindForTool } from '../../store/mainWindow';

export function useDispatchCommand() {
  const openMainWindow = useMainWindowStore((s) => s.openMainWindow);
  const [isDispatching, setIsDispatching] = useState(false);

  const dispatch = useCallback(
    async (text: string) => {
      setIsDispatching(true);
      try {
        await postStream({
          path: '/dispatch',
          body: { content: text },
          onEvent: (e) => {
            if (e.event === 'function_call_output' && e.success) {
              const kind = viewKindForTool(e.tool_name ?? null);
              if (kind) openMainWindow({ kind, data: e.data ?? undefined });
            }
          },
        });
      } finally {
        setIsDispatching(false);
      }
    },
    [openMainWindow],
  );

  return { dispatch, isDispatching };
}
