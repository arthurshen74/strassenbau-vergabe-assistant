// Typed SSE event helpers. The server emits events conforming to SSEEvent
// from generated.ts (see ARCHITECTURE.md §8). Each line of an SSE message
// is `event: <name>` followed by `data: <json>`. We parse to the union.

import type {
  ConsoleJobsSnapshot,
  IngestActivityLine,
  IngestEvent,
  ProjectInfoActivityLine,
  SSEEvent,
} from '../types/generated';

export type SSEEventName = SSEEvent['event'];

function parsePayload<T>(eventName: string, dataJson: string): T | null {
  try {
    const data = JSON.parse(dataJson);
    return { event: eventName, ...data } as T;
  } catch {
    return null;
  }
}

export function parseSSEPayload(eventName: string, dataJson: string): SSEEvent | null {
  return parsePayload<SSEEvent>(eventName, dataJson);
}

export function parseIngestPayload(eventName: string, dataJson: string): IngestEvent | null {
  return parsePayload<IngestEvent>(eventName, dataJson);
}

export function parseActivityPayload(
  eventName: string,
  dataJson: string,
): IngestActivityLine | null {
  return parsePayload<IngestActivityLine>(eventName, dataJson);
}

export function parseProjectInfoActivityPayload(
  eventName: string,
  dataJson: string,
): ProjectInfoActivityLine | null {
  return parsePayload<ProjectInfoActivityLine>(eventName, dataJson);
}

export function parseConsoleJobsPayload(
  eventName: string,
  dataJson: string,
): ConsoleJobsSnapshot | null {
  return parsePayload<ConsoleJobsSnapshot>(eventName, dataJson);
}

export function isTerminal(e: SSEEvent): boolean {
  return e.event === 'done';
}
