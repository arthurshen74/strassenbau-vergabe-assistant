// EKT calculator run API. The flow is conversation-first:
//   - createCalculation: POST to make the ekt_calculator conversation, returns it (no stream).
//   - streamCalculation: POST to run the graph and consume the SSEEvent stream until interrupt/done.
//   - resumeCalculation: POST the Kalkulator's decision to continue a paused run.
// Follow-up questions after the run completes go through the normal conversation /turn endpoint.

import { api } from './client';
import { postStream } from './sse';
import type { ConversationRead, SSEEvent } from '../types/generated';

// The Kalkulator's structured decision for the current interrupt; the fields the paused stage reads.
export interface CalculationResume {
  work_type?: string;
  drivers?: Record<string, unknown>;
  action?: string;
}

export function createCalculation(projectUuid: string, oz: string): Promise<ConversationRead> {
  return api.post<ConversationRead>(
    `/projects/${projectUuid}/lv-items/${encodeURIComponent(oz)}/calculations`,
  );
}

export interface StreamCalculationOptions {
  conversationId: string;
  onEvent: (event: SSEEvent) => void;
  signal?: AbortSignal;
}

export function streamCalculation({
  conversationId,
  onEvent,
  signal,
}: StreamCalculationOptions): Promise<void> {
  return postStream({
    path: `/conversations/${conversationId}/calculation/stream`,
    body: {},
    onEvent,
    signal,
  });
}

export interface ResumeCalculationOptions {
  conversationId: string;
  decision: CalculationResume;
  onEvent: (event: SSEEvent) => void;
  signal?: AbortSignal;
}

export function resumeCalculation({
  conversationId,
  decision,
  onEvent,
  signal,
}: ResumeCalculationOptions): Promise<void> {
  return postStream({
    path: `/conversations/${conversationId}/calculation/resume`,
    body: decision,
    onEvent,
    signal,
  });
}
