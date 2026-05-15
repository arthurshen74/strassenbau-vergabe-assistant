// Thin fetch wrapper. Centralizes base URL, JSON handling, and error
// shape so query hooks stay terse. SSE has its own client (see sse.ts)
// because EventSource needs different lifecycle handling.

import { APP_CONSTANTS } from '../appconstants';
import { log } from '../lib/logger';

const API_BASE = '/api';

export class ApiError extends Error {
  status: number;
  body: unknown;
  requestId: string | null;
  constructor(
    status: number,
    message: string,
    body: unknown,
    requestId: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.body = body;
    this.requestId = requestId;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  init?: RequestInit,
  timeoutMs: number = APP_CONSTANTS.API_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(new DOMException('Request timed out', 'TimeoutError')),
    timeoutMs,
  );

  const startedAt = performance.now();
  log.api(`→ ${method} ${path}`);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      ...init,
    });
    const ms = Math.round(performance.now() - startedAt);
    const requestId = res.headers.get('X-Request-Id');
    if (!res.ok) {
      let parsed: unknown = null;
      try {
        parsed = await res.json();
      } catch {
        // body wasn't JSON; ignore
      }
      log.api.error(
        `← ${method} ${path} → ${res.status}`,
        { ms, requestId, body: parsed },
      );
      throw new ApiError(
        res.status,
        `${method} ${path} → ${res.status}`,
        parsed,
        requestId,
      );
    }
    log.api(`← ${method} ${path} → ${res.status}`, { ms, requestId });
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown, timeoutMs?: number) =>
    request<T>('POST', path, body, undefined, timeoutMs),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
};

export const apiBase = API_BASE;
