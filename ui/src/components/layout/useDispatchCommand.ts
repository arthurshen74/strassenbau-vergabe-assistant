// Single-shot dispatcher command: POST /dispatch and, on a routable tool result, open the matching
// main window. No conversation is created and nothing is persisted — the dispatcher is stateless.
//
// When the dispatcher can't route a request it streams text (its fallback message) instead of a
// tool call. We accumulate that text into `message` so the bar can show it; opening a window clears
// it (the route succeeded, there's nothing to say).

import { useCallback, useState } from 'react';
import { postStream } from '../../api/sse';
import { useMainWindowStore, viewKindForTool } from '../../store/mainWindow';

export function useDispatchCommand() {
  const openMainWindow = useMainWindowStore((s) => s.openMainWindow);
  const [isDispatching, setIsDispatching] = useState(false);
  const [message, setMessage] = useState('');

  const dispatch = useCallback(
    async (text: string) => {
      setIsDispatching(true);
      setMessage('');
      let accumulated = '';
      try {
        await postStream({
          path: '/dispatch',
          body: { content: text },
          onEvent: (e) => {
            if (e.event === 'text_delta' || e.event === 'ui_notice') {
              accumulated += e.content;
              setMessage(accumulated);
            } else if (e.event === 'function_call_output' && e.success) {
              const kind = viewKindForTool(e.tool_name ?? null);
              if (kind) {
                accumulated = '';
                setMessage('');
                openMainWindow({ kind, data: e.data ?? undefined });
              }
            }
          },
        });
      } finally {
        setIsDispatching(false);
      }
    },
    [openMainWindow],
  );

  const clearMessage = useCallback(() => setMessage(''), []);

  return { dispatch, isDispatching, message, clearMessage };
}
