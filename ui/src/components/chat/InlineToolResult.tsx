// Card chrome for successful tool results rendered inline in the message
// list. Keeps individual tool components focused on their content.

import clsx from 'clsx';

interface InlineToolResultProps {
  children: React.ReactNode;
  className?: string;
}

export function InlineToolResult({
  children,
  className,
}: InlineToolResultProps) {
  return (
    <div
      className={clsx(
        'w-full rounded-lg border border-zinc-950/10 bg-white p-4 shadow-sm',
        'dark:border-white/10 dark:bg-zinc-900',
        className,
      )}
    >
      {children}
    </div>
  );
}
