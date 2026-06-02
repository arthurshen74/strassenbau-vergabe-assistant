// Display-message union for the chat list.
//
// Persisted messages are `MessageRead` (kinds: user / assistant /
// function_call / function_call_output). `ui_notice` is NOT a persisted
// kind — it only ever arrives as a live SSE event and lives in the local
// stream buffer — so it gets its own ephemeral shape here.

import type { MessageRead } from '../../types/generated';

export interface UiNoticeMessage {
  message_uuid: string;
  conversation_uuid: string;
  kind: 'ui_notice';
  content: string;
  created_at: string;
}

export type DisplayMessage = MessageRead | UiNoticeMessage;
