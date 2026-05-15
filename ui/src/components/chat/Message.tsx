// Discriminated-union dispatch on message kind. The `never`-assignment
// in the default branch is the compile-time exhaustiveness check: when
// a new message kind lands in generated.ts and we forget to handle it,
// the build fails here.

import type {
  FunctionCallOutputMessageDTO,
  MessageDTO,
} from '../../types/generated';
import { UserMessage } from './messages/UserMessage';
import { AssistantMessage } from './messages/AssistantMessage';
import { InterviewerMessage } from './messages/InterviewerMessage';
import { CandidateMessage } from './messages/CandidateMessage';
import { UINoticeMessage } from './messages/UINoticeMessage';
import { FunctionCallOutputMessage } from './messages/FunctionCallOutputMessage';

interface MessageProps {
  m: MessageDTO;
  /** Optional flag indicating this message is currently being streamed. */
  streaming?: boolean;
  renderToolResult?: (msg: FunctionCallOutputMessageDTO) => React.ReactNode;
}

export function Message({ m, streaming, renderToolResult }: MessageProps) {
  switch (m.kind) {
    case 'user_message':
      return <UserMessage m={m} />;
    case 'assistant_message':
      return <AssistantMessage m={m} streaming={streaming} />;
    case 'interviewer_message':
      return <InterviewerMessage m={m} streaming={streaming} />;
    case 'candidate_message':
      return <CandidateMessage m={m} />;
    case 'ui_notice':
      return <UINoticeMessage m={m} />;
    case 'function_call':
      // Protocol-only; not rendered. See FRONTEND.md §4.
      return null;
    case 'function_call_output':
      return (
        <FunctionCallOutputMessage m={m} renderToolResult={renderToolResult} />
      );
    default: {
      const _exhaustive: never = m;
      void _exhaustive;
      return null;
    }
  }
}
