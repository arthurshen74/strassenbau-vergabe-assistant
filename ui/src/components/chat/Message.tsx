// Discriminated-union dispatch on message kind. The `never`-assignment in
// the default branch is the compile-time exhaustiveness check: when a new
// kind lands and we forget to handle it, the build fails here.
//
// Tool messages (function_call / function_call_output) are protocol-only and
// never rendered inline — successful tool output surfaces in the main window.

import type { DisplayMessage } from './types';
import { UserMessage } from './messages/UserMessage';
import { AssistantMessage } from './messages/AssistantMessage';
import { UINoticeMessage } from './messages/UINoticeMessage';

interface MessageProps {
  m: DisplayMessage;
  streaming?: boolean;
}

export function Message({ m, streaming }: MessageProps) {
  switch (m.kind) {
    case 'user':
      return <UserMessage content={m.content ?? ''} />;
    case 'assistant':
      return <AssistantMessage content={m.content ?? ''} streaming={streaming} />;
    case 'ui_notice':
      return <UINoticeMessage content={m.content} />;
    case 'function_call':
    case 'function_call_output':
      return null;
    default: {
      const _exhaustive: never = m;
      void _exhaustive;
      return null;
    }
  }
}
