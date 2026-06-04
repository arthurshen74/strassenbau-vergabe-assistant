// Discriminated-union dispatch on message kind. The `never`-assignment in
// the default branch is the compile-time exhaustiveness check: when a new
// kind lands and we forget to handle it, the build fails here.
//
// function_call is protocol-only (never shown). function_call_output renders
// inline for project-chat tools (LV results, retrieval sources); the dispatcher's
// tools open the main window instead and render nothing here.

import type { DisplayMessage } from './types';
import { UserMessage } from './messages/UserMessage';
import { AssistantMessage } from './messages/AssistantMessage';
import { UINoticeMessage } from './messages/UINoticeMessage';
import { ToolResultMessage } from './messages/ToolResultMessage';
import type { CitationData } from './messages/CitationsPanel';

interface MessageProps {
  m: DisplayMessage;
  streaming?: boolean;
  /** Merged retrieval sources for this turn, attached to the assistant answer's citations. */
  citationData?: CitationData | null;
  projectUuid?: string;
}

export function Message({ m, streaming, citationData, projectUuid }: MessageProps) {
  switch (m.kind) {
    case 'user':
      return <UserMessage content={m.content ?? ''} />;
    case 'assistant':
      return (
        <AssistantMessage
          content={m.content ?? ''}
          streaming={streaming}
          citationData={citationData}
          projectUuid={projectUuid}
        />
      );
    case 'ui_notice':
      return <UINoticeMessage content={m.content} level={m.level} />;
    case 'function_call':
      return null;
    case 'function_call_output':
      return <ToolResultMessage m={m} projectUuid={projectUuid} />;
    default: {
      const _exhaustive: never = m;
      void _exhaustive;
      return null;
    }
  }
}
