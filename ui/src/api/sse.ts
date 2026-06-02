// Fetch-based SSE consumers.
//
// EventSource only supports GET with no custom headers; our streams are either
// "POST a message, receive a stream" (chat) or a long-lived GET (ingest status).
// So we use fetch + ReadableStream and parse the SSE wire format by hand. Both
// share one reader (`runStream`); the chat and ingest entry points differ only in
// method and in the typed parser they hand it.
//
// These are NOT hooks — call them inside a mutation or an effect.

import { apiBase } from './client';
import { log } from '../lib/logger';
import { parseSSEPayload } from '../lib/sse-events';
import type { SSEEvent } from '../types/generated';

interface RunStreamOptions<T extends { event: string }> {
  path: string;
  method: 'GET' | 'POST';
  body?: unknown;
  parse: (eventName: string, dataJson: string) => T | null;
  onEvent: (event: T) => void;
  signal?: AbortSignal;
}

async function runStream<T extends { event: string }>({
  path,
  method,
  body,
  parse,
  onEvent,
  signal,
}: RunStreamOptions<T>): Promise<void> {
  const startedAt = performance.now();
  log.sse('stream_start', { path });
  const res = await fetch(`${apiBase}${path}`, {
    method,
    headers: {
      Accept: 'text/event-stream',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!res.ok || !res.body) {
    log.sse.error('stream_failed', { path, status: res.status });
    throw new Error(`Stream failed: ${res.status} ${res.statusText}`);
  }
  const requestId = res.headers.get('X-Request-Id');
  log.sse('stream_open', { path, requestId });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventCount = 0;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by a blank line. Split, keep the trailing
      // partial chunk in the buffer.
      let separatorIdx;
      while ((separatorIdx = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, separatorIdx);
        buffer = buffer.slice(separatorIdx + 2);
        const parsed = parseSSEMessage(raw, parse);
        if (parsed) {
          eventCount += 1;
          // text_delta is per-token; logging each one drowns the firehose.
          if (parsed.event !== 'text_delta') log.sse(parsed.event, parsed);
          onEvent(parsed);
        }
      }
    }
  } finally {
    const ms = Math.round(performance.now() - startedAt);
    log.sse('stream_end', { path, ms, events: eventCount, requestId });
  }
}

function parseSSEMessage<T extends { event: string }>(
  raw: string,
  parse: (eventName: string, dataJson: string) => T | null,
): T | null {
  // Parse `event: NAME` and `data: {...}` lines. Multiple `data:` lines
  // concatenate with newlines per spec; our backend writes one data line.
  let eventName = 'message';
  const dataLines: string[] = [];
  for (const line of raw.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    if (colon === -1) continue;
    const field = line.slice(0, colon);
    // SSE allows a single optional space after the colon.
    const value =
      line[colon + 1] === ' ' ? line.slice(colon + 2) : line.slice(colon + 1);
    if (field === 'event') eventName = value;
    else if (field === 'data') dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  return parse(eventName, dataLines.join('\n'));
}

export interface PostStreamOptions {
  path: string;
  body: unknown;
  onEvent: (event: SSEEvent) => void;
  signal?: AbortSignal;
}

// Chat: POST a turn, consume the SSEEvent stream.
export function postStream({
  path,
  body,
  onEvent,
  signal,
}: PostStreamOptions): Promise<void> {
  return runStream<SSEEvent>({ path, method: 'POST', body, parse: parseSSEPayload, onEvent, signal });
}

export interface EventStreamOptions<T extends { event: string }> {
  path: string;
  parse: (eventName: string, dataJson: string) => T | null;
  onEvent: (event: T) => void;
  signal?: AbortSignal;
}

// Long-lived GET stream (e.g. ingest status), parsed into a caller-supplied union.
export function openEventStream<T extends { event: string }>({
  path,
  parse,
  onEvent,
  signal,
}: EventStreamOptions<T>): Promise<void> {
  return runStream<T>({ path, method: 'GET', parse, onEvent, signal });
}
