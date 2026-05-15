// Dispatches a successful function_call_output message to the right
// inline renderer based on tool_name.
//
// We keep the data field typed as `unknown` and narrow inside each
// renderer (cast at the boundary). Producing strongly-typed
// per-tool output DTOs would couple the frontend to the tool catalog
// in a way the spec explicitly avoids — output shape is whatever the
// service layer returns, and that's allowed to evolve.

import type { FunctionCallOutputMessageDTO } from '../../../types/generated';
import { ProfileCard } from './ProfileCard';
import { PositionList } from './PositionList';
import { PositionCard } from './PositionCard';
import { ArchivedNotice } from './ArchivedNotice';
import { PromptList } from './PromptList';
import { PromptGroupCard } from './PromptGroupCard';

interface ToolResultRouterProps {
  msg: FunctionCallOutputMessageDTO;
  /**
   * Workspace send-message callback. Threaded to tool-result components
   * that let the user navigate further (e.g. clicking a prompt row
   * to open its detail). When undefined the components render as static
   * summaries (historical messages outside an active workspace session).
   */
  onSendMessage?: (text: string) => void;
}

export function ToolResultRouter({ msg, onSendMessage }: ToolResultRouterProps) {
  switch (msg.tool_name) {
    case 'view_profile':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <ProfileCard data={msg.data as any} variant="view" />;
    case 'update_profile':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <ProfileCard data={msg.data as any} variant="update" />;
    case 'list_positions':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <PositionList data={msg.data as any} interactive={!!onSendMessage} />;
    case 'view_position':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <PositionCard data={msg.data as any} variant="view" />;
    case 'add_position':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <PositionCard data={msg.data as any} variant="created" />;
    case 'modify_position':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <PositionCard data={msg.data as any} variant="modified" />;
    case 'archive_position':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <ArchivedNotice data={msg.data as any} />;
    case 'list_prompts':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <PromptList data={msg.data as any} interactive={!!onSendMessage} />;
    case 'view_prompt':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <PromptGroupCard data={msg.data as any} variant="view" />;
    case 'edit_prompt':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <PromptGroupCard data={msg.data as any} variant="edited" />;
    case 'archive_prompt':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return <PromptGroupCard data={msg.data as any} variant="archived" />;
    // Session tools: navigation (start) or sidebar refresh (list/delete)
    // handle the UX — no inline card needed. Returning null suppresses the
    // default JSON dump; FunctionCallOutputMessage skips the InlineToolResult
    // wrapper when content is null.
    case 'start_prep_session':
    case 'list_prep_sessions':
    case 'delete_prep_session':
      return null;
    default:
      return (
        <pre className="overflow-auto text-xs text-zinc-700 dark:text-zinc-300">
          {JSON.stringify(msg.data, null, 2)}
        </pre>
      );
  }
}
