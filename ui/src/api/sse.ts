// POST-then-stream SSE consumer.
//
// EventSource only supports GET, but our protocol is "POST a message,
// receive a stream". So we use fetch + ReadableStream and parse the SSE
// wire format by hand. The parser handles multi-line events and dispatches
// each parsed envelope through the provided onEvent callback.
//
// This is NOT a hook — it's a function you call inside a mutation or
// effect. Hooks would force us to model "stream is starting" as React
// state, which fights the imperative nature of submit-then-consume.

import { apiBase } from './client';
import { log } from '../lib/logger';
import { parseSSEPayload } from '../lib/sse-events';
import type { SSEEvent } from '../types/generated';

export interface PostStreamOptions {
  path: string;
  body: unknown;
  onEvent: (event: SSEEvent) => void;
  signal?: AbortSignal;
}

export async function postStream({
  path,
  body,
  onEvent,
  signal,
}: PostStreamOptions): Promise<void> {
  const startedAt = performance.now();
  log.sse('stream_start', { path });
  const res = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
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
        const parsed = parseSSEMessage(raw);
        if (parsed) {
          eventCount += 1;
          // text_delta is per-token; logging each one drowns the firehose.
          // Aggregate-only signals (start/end of stream) are enough for that
          // event, the rest get full payloads.
          if (parsed.event !== 'text_delta') {
            log.sse(parsed.event, parsed);
          }
          onEvent(parsed);
        }
      }
    }
  } finally {
    const ms = Math.round(performance.now() - startedAt);
    log.sse('stream_end', { path, ms, events: eventCount, requestId });
  }
}

function parseSSEMessage(raw: string): SSEEvent | null {
  // Parse `event: NAME` and `data: {...}` lines. Multiple `data:` lines
  // would concatenate with newlines per spec, but our backend writes a
  // single data line per message.
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
  return parseSSEPayload(eventName, dataLines.join('\n'));
}
