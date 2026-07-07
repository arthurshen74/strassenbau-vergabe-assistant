// Live agent-activity trail for a streaming turn: one step per tool call the
// agent makes, built from the function_call / function_call_output SSE events
// and rendered inside the ThinkingIndicator while the answer is pending.

import {
  TOOL_AGGREGATE_LV_ITEMS,
  TOOL_GET_LV_ALL,
  TOOL_GET_LV_CONTEXT,
  TOOL_GET_LV_GROUP_ITEMS,
  TOOL_GET_LV_SINGLE_ITEM,
  TOOL_GET_PROJECT_CONTEXT,
  TOOL_RENDER_MAP,
} from './messages/ToolResultMessage';

// The control signal a position chat emits to start its EKT calculation (project_chat_agent.py).
const TOOL_CALCULATE_EKT = 'calculate_ekt';

export interface AgentActivityStep {
  callId: string;
  toolName: string;
  /** Short excerpt of the call's arguments (query, code, …), for the label. */
  hint: string | null;
  done: boolean;
}

// German labels for the project-chat agent's English wire names. Katalog tools are already
// German snake_case and read fine through the title-case fallback.
const TOOL_LABEL: Record<string, string> = {
  [TOOL_GET_PROJECT_CONTEXT]: 'Durchsuche Projektdokumente',
  [TOOL_GET_LV_CONTEXT]: 'Durchsuche das Leistungsverzeichnis',
  [TOOL_GET_LV_ALL]: 'Lese das Leistungsverzeichnis',
  [TOOL_GET_LV_SINGLE_ITEM]: 'Lese LV-Position',
  [TOOL_GET_LV_GROUP_ITEMS]: 'Lese LV-Gruppe',
  [TOOL_AGGREGATE_LV_ITEMS]: 'Aggregiere LV-Mengen',
  [TOOL_RENDER_MAP]: 'Erzeuge Karte',
  [TOOL_CALCULATE_EKT]: 'Starte EKT-Kalkulation',
};

const HINT_MAX_CHARS = 60;

export function toolActivityLabel(step: AgentActivityStep): string {
  const base =
    TOOL_LABEL[step.toolName] ??
    step.toolName
      .split('_')
      .filter(Boolean)
      .map((w) => w[0].toUpperCase() + w.slice(1))
      .join(' ');
  return step.hint ? `${base}: ${step.hint}` : base;
}

/** The first primitive argument value, as a short excerpt for the activity label. */
export function toolActivityHint(args: Record<string, unknown>): string | null {
  for (const value of Object.values(args)) {
    if (typeof value === 'string' && value.trim()) {
      const text = value.trim();
      return text.length > HINT_MAX_CHARS ? `${text.slice(0, HINT_MAX_CHARS)}…` : text;
    }
    if (typeof value === 'number') return String(value);
  }
  return null;
}
