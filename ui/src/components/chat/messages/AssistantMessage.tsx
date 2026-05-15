import type { AssistantMessageDTO } from '../../../types/generated';
import { StreamingText } from '../StreamingText';

interface AssistantMessageProps {
  m: AssistantMessageDTO;
  streaming?: boolean;
}

export function AssistantMessage({ m, streaming = false }: AssistantMessageProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-2xl text-sm whitespace-pre-wrap text-zinc-900 dark:text-zinc-100">
        <StreamingText text={m.content} streaming={streaming} />
      </div>
    </div>
  );
}
