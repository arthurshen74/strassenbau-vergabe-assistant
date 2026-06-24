// EKT calculator API. A calculation lives inside a position chat (ekt_calculator conversation):
//   - createCalculation: POST to make the position-chat conversation for an LV position, returns it.
// Running the calculation, streaming its reasoning, and resuming across HITL gates all happen
// through the conversation /turn endpoint (see useWorkspaceConversation): a chat message can ask to
// calculate, and a paused gate is answered with a structured `resume` payload.

import { api } from './client';
import type { ConversationRead } from '../types/generated';

// The Kalkulator's structured decision for the current HITL gate; the fields the paused stage reads.
//   - method_review (Gate A): confirm the Leistung and select the Bauverfahren.
//   - variable_review (Gate B): overrides maps a variable name -> its corrected value (changed leaves only).
export interface CalculationResume {
  leistung_key?: string;
  bauverfahren_key?: string;
  overrides?: Record<string, unknown>;
  cancel?: boolean;
}

export function createCalculation(projectUuid: string, oz: string): Promise<ConversationRead> {
  return api.post<ConversationRead>(
    `/projects/${projectUuid}/lv-items/${encodeURIComponent(oz)}/calculations`,
  );
}
