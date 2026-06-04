// Typed SSE event helpers. The server emits events conforming to SSEEvent
// from generated.ts (see ARCHITECTURE.md §8). Each line of an SSE message
// is `event: <name>` followed by `data: <json>`. We parse to the union.

import type { IngestActivityLine, IngestEvent, SSEEvent } from '../types/generated';

export type SSEEventName = SSEEvent['event'];

export function parseSSEPayload(eventName: string, dataJson: string): SSEEvent | null {
  try {
    const data = JSON.parse(dataJson);
    return { event: eventName, ...data } as SSEEvent;
  } catch {
    return null;
  }
}

export function parseIngestPayload(eventName: string, dataJson: string): IngestEvent | null {
  try {
    const data = JSON.parse(dataJson);
    return { event: eventName, ...data } as IngestEvent;
  } catch {
    return null;
  }
}

export function parseActivityPayload(
  eventName: string,
  dataJson: string,
): IngestActivityLine | null {
  try {
    const data = JSON.parse(dataJson);
    return { event: eventName, ...data } as IngestActivityLine;
  } catch {
    return null;
  }
}

export function isTerminal(e: SSEEvent): boolean {
  return e.event === 'done';
}
