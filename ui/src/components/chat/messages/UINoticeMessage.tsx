import type { UINoticeMessageDTO } from '../../../types/generated';

export function UINoticeMessage({ m }: { m: UINoticeMessageDTO }) {
  return (
    <div className="flex justify-center">
      <div className="text-xs italic text-zinc-500 dark:text-zinc-400">
        {m.content}
      </div>
    </div>
  );
}
