import type { InterviewerMessageDTO } from '../../../types/generated';
import { StreamingText } from '../StreamingText';

interface Props {
  m: InterviewerMessageDTO;
  streaming?: boolean;
}

export function InterviewerMessage({ m, streaming = false }: Props) {
  return (
    <div className="flex justify-start">
      <div className="max-w-2xl rounded-2xl border border-zinc-950/10 px-4 py-2 text-sm text-zinc-900 dark:border-white/10 dark:text-zinc-100">
        <div className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
          Q{m.question_number}
        </div>
        <div className="whitespace-pre-wrap">
          <StreamingText text={m.content} streaming={streaming} />
        </div>
      </div>
    </div>
  );
}
