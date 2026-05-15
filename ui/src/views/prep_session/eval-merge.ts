// Pure function for merging an incoming eval_update event into the
// cached eval scores map.
//
// Out-of-order merge rule (ARCHITECTURE.md §9):
//   The eval bus publishes events in completion order, not turn order.
//   eval(N) can land after eval(N+1). We accept an incoming event only
//   if its after_message_created_at is >= the stored entry's. Stale
//   arrivals are dropped; their EvalScore rows persist server-side for
//   judge runs.

import type { EvalScoreDTO, EvalUpdateEvent } from '../../types/generated';

export type EvalScoreCache = Record<string, EvalScoreDTO>;

export function mergeEvalUpdate(
  prev: EvalScoreCache | undefined,
  event: EvalUpdateEvent,
): EvalScoreCache {
  const current = prev ?? {};
  const existing = current[event.dimension];

  if (existing) {
    const existingTs = new Date(existing.created_at).getTime();
    const incomingTs = new Date(event.after_message_created_at).getTime();
    if (incomingTs < existingTs) {
      // Stale arrival — drop it.
      return current;
    }
  }

  const updated: EvalScoreDTO = {
    // We don't have a server-issued id for live events; use a stable key.
    id: `live-${event.dimension}-${event.after_message_id}`,
    session_id: '',
    after_message_id: event.after_message_id,
    dimension: event.dimension,
    score: event.score,
    rationale: event.rationale,
    // Use a placeholder prompt id/version — the drawer only needs
    // score + rationale + created_at for rendering.
    evaluator_prompt_id: '',
    evaluator_prompt_version: 0,
    created_at: event.after_message_created_at,
  };

  return { ...current, [event.dimension]: updated };
}
