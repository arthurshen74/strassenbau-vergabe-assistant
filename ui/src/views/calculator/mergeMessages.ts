// Merge server-persisted messages with the in-flight stream buffer, deduped by id (server wins) and
// sorted by created_at. Shared by the calculator's gate and run phases.

import type { MessageRead } from '../../types/generated';
import type { DisplayMessage } from '../../components/chat/types';

export function mergeMessages(
  persisted: MessageRead[] | undefined,
  stream: DisplayMessage[],
): DisplayMessage[] {
  const byId = new Map<string, DisplayMessage>();
  for (const m of persisted ?? []) byId.set(m.message_uuid, m);
  for (const m of stream) if (!byId.has(m.message_uuid)) byId.set(m.message_uuid, m);
  return [...byId.values()].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
}
