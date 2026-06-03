import { ExclamationTriangleIcon } from '@heroicons/react/16/solid';
import type { SSEUiNotice } from '../../../types/generated';

interface UINoticeMessageProps {
  content: string;
  level?: SSEUiNotice['level'];
}

export function UINoticeMessage({ content, level = 'info' }: UINoticeMessageProps) {
  if (level === 'error') {
    return (
      <div className="flex justify-center">
        <div className="flex items-center gap-1.5 rounded-md border border-red-500/20 bg-red-500/5 px-3 py-1.5 text-xs text-red-600 dark:text-red-400">
          <ExclamationTriangleIcon className="h-3.5 w-3.5 shrink-0" />
          <span>{content}</span>
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-center">
      <div className="text-xs italic text-zinc-500 dark:text-zinc-400">{content}</div>
    </div>
  );
}
