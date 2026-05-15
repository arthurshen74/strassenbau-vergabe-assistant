import type { CandidateMessageDTO } from '../../../types/generated';

export function CandidateMessage({ m }: { m: CandidateMessageDTO }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-2xl rounded-2xl bg-zinc-200 px-4 py-2 text-sm whitespace-pre-wrap text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100">
        {m.content}
      </div>
    </div>
  );
}
