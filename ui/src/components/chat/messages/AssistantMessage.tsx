import { StreamingText } from '../StreamingText';

interface AssistantMessageProps {
  content: string;
  streaming?: boolean;
}

export function AssistantMessage({ content, streaming = false }: AssistantMessageProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-2xl text-sm whitespace-pre-wrap text-zinc-900 dark:text-zinc-100">
        <StreamingText text={content} streaming={streaming} />
      </div>
    </div>
  );
}
