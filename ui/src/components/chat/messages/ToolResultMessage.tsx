// Routes a persisted function_call_output to its inline renderer by tool name.
// LV results render in the thread; retrieval renders only its verbose trace here
// (the sources move below the answer, see CitationsPanel). Dispatcher tools open the
// main window instead and render nothing here.

import type { MessageRead } from '../../../types/generated';
import { LvResultMessage } from './LvResultMessage';
import { RetrievalTraceMessage } from './RetrievalTraceMessage';

// Wire tool names, matching the names ProjectChatService emits.
export const TOOL_LV_ITEM = 'view_lvitem';
export const TOOL_LV_ITEMS = 'view_lvitems';
export const TOOL_GET_CONTEXT = 'get_context';

export function ToolResultMessage({ m }: { m: MessageRead }) {
  if (!m.success) return null;
  switch (m.tool_name) {
    case TOOL_LV_ITEM:
    case TOOL_LV_ITEMS:
      return <LvResultMessage data={m.data ?? null} />;
    case TOOL_GET_CONTEXT:
      return <RetrievalTraceMessage data={m.data ?? null} />;
    default:
      return null;
  }
}
