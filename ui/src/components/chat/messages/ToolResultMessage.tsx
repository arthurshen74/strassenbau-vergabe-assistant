// Routes a persisted function_call_output to its inline renderer by tool name.
// LV results and aggregates render in the thread; the context tools render only their verbose
// trace here (the sources move below the answer, see CitationsPanel). Dispatcher tools open the
// main window instead and render nothing here.

import type { MessageRead } from '../../../types/generated';
import { AggregateResultMessage } from './AggregateResultMessage';
import { EktResultMessage } from './EktResultMessage';
import { LvResultMessage } from './LvResultMessage';
import { MapResultMessage } from './MapResultMessage';
import { RetrievalTraceMessage } from './RetrievalTraceMessage';

// Wire tool names, matching the names the project-chat agent emits (ProjectChatAgent tools).
export const TOOL_GET_PROJECT_CONTEXT = 'get_project_context';
export const TOOL_GET_LV_CONTEXT = 'get_lv_context';
export const TOOL_GET_LV_ALL = 'get_lv_all';
export const TOOL_GET_LV_SINGLE_ITEM = 'get_lv_single_item';
export const TOOL_GET_LV_GROUP_ITEMS = 'get_lv_group_items';
export const TOOL_AGGREGATE_LV_ITEMS = 'aggregate_lv_items';
export const TOOL_RENDER_MAP = 'render_map';
// Emitted by the EKT calculator run (CalculatorRunService), not a project-chat tool.
export const TOOL_EKT_RESULT = 'ekt_result';

export function ToolResultMessage({
  m,
  projectUuid,
}: {
  m: MessageRead;
  projectUuid?: string;
}) {
  if (!m.success) return null;
  switch (m.tool_name) {
    case TOOL_GET_PROJECT_CONTEXT:
    case TOOL_GET_LV_CONTEXT:
      return <RetrievalTraceMessage data={m.data ?? null} />;
    case TOOL_GET_LV_SINGLE_ITEM:
    case TOOL_GET_LV_ALL:
    case TOOL_GET_LV_GROUP_ITEMS:
      return <LvResultMessage data={m.data ?? null} projectUuid={projectUuid} />;
    case TOOL_AGGREGATE_LV_ITEMS:
      return (
        <AggregateResultMessage data={m.data ?? null} projectUuid={projectUuid} />
      );
    case TOOL_RENDER_MAP:
      return <MapResultMessage data={m.data ?? null} projectUuid={projectUuid} />;
    case TOOL_EKT_RESULT:
      return <EktResultMessage data={m.data ?? null} />;
    default:
      return null;
  }
}
