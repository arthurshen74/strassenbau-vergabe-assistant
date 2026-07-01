// EKT calculator API. A calculation lives inside a position chat (ekt_calculator conversation):
//   - createCalculation: POST to make the position-chat conversation for an LV position, returns it.
// Running the calculation, streaming its reasoning, and resuming across HITL gates all happen
// through the conversation /turn endpoint (see useWorkspaceConversation): a chat message can ask to
// calculate, and a paused gate is answered with a structured `resume` payload.

import { api } from './client';
import type { ConversationRead } from '../types/generated';

// The Kalkulator's structured decision for the current HITL gate; the fields the paused stage reads.
//   - project_context_review (pre-Gate-A): projekt_kontext maps a changed global -> its new value
//     (locations as address strings, strip dims/Fräsgut as numbers); only changed fields are sent.
//   - method_review (Gate A): confirm the Leistung and select the Bauverfahren.
//   - variable_review (Gate B): overrides maps a variable name -> its corrected value (changed leaves only);
//     reasons optionally tags each override, and mark_as_ground_truth saves the review as eval ground truth.
export interface CalculationResume {
  projekt_kontext?: Record<string, string>; // pre-Gate-A: changed project globals -> new value
  leistung_key?: string;
  bauverfahren_key?: string;
  maschinen?: Record<string, string>;      // Ausführungsart slot code -> Maschine code (Gate A)
  baustoff_code?: string;
  lieferanten?: Record<string, string>;    // baustoff_code -> Lieferant code (Gate A, per material)
  overrides?: Record<string, unknown>;
  reasons?: Record<string, string>;        // Gate B: variable name -> why it was overridden
  mark_as_ground_truth?: boolean;          // Gate B: save the reviewed state as ground truth
  cancel?: boolean;
}

export function createCalculation(projectUuid: string, oz: string): Promise<ConversationRead> {
  return api.post<ConversationRead>(
    `/projects/${projectUuid}/lv-items/${encodeURIComponent(oz)}/calculations`,
  );
}
