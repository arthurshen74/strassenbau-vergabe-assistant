// Animated "thinking" feedback shown while an LLM response is in flight.
//
// Two sizes:
//   sm  — three small bouncing dots; used next to the chat input (ChatInput
//         already renders this via the `hint` text, but you can drop this
//         component anywhere a compact indicator is needed).
//   lg  — full-width card with a pulsing brain/sparkle icon, animated dots,
//         and a label; used in the inline PromptTester chat.

import clsx from 'clsx';

interface ThinkingIndicatorProps {
  size?: 'sm' | 'lg';
  label?: string;
  className?: string;
}

/** Three bouncing dots (shared by both sizes). */
function Dots({ dotClass }: { dotClass?: string }) {
  return (
    <span className="inline-flex items-center gap-1" aria-hidden>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{ animationDelay: `${i * 160}ms` }}
          className={clsx(
            'inline-block rounded-full bg-current animate-bounce',
            dotClass ?? 'h-1.5 w-1.5',
          )}
        />
      ))}
    </span>
  );
}

export function ThinkingIndicator({
  size = 'lg',
  label = 'Thinking',
  className,
}: ThinkingIndicatorProps) {
  if (size === 'sm') {
    return (
      <span
        role="status"
        aria-label={label}
        className={clsx('inline-flex items-center gap-1.5 text-zinc-400 dark:text-zinc-500', className)}
      >
        <Dots dotClass="h-1 w-1" />
        <span className="sr-only">{label}</span>
      </span>
    );
  }

  // lg — prominent card for the inline chat
  return (
    <div
      role="status"
      aria-label={label}
      className={clsx(
        'flex items-center gap-3 rounded-xl border border-zinc-950/10 bg-white px-5 py-4 shadow-sm',
        'dark:border-white/10 dark:bg-zinc-900',
        className,
      )}
    >
      {/* Pulsing ring + icon */}
      <span className="relative flex h-9 w-9 shrink-0 items-center justify-center">
        {/* outer pulse */}
        <span className="absolute inset-0 animate-ping rounded-full bg-violet-400/30 dark:bg-violet-500/20" />
        {/* inner circle */}
        <span className="relative flex h-9 w-9 items-center justify-center rounded-full bg-violet-100 dark:bg-violet-900/40">
          {/* sparkle SVG */}
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-5 w-5 text-violet-600 dark:text-violet-400"
            aria-hidden
          >
            <path
              fillRule="evenodd"
              d="M10.868 2.884c-.321-.772-1.415-.772-1.736 0l-1.83 4.401-4.753.381c-.833.067-1.171 1.107-.536 1.651l3.62 3.102-1.106 4.637c-.194.813.691 1.456 1.405 1.02L10 15.591l4.069 2.485c.713.436 1.598-.207 1.404-1.02l-1.106-4.637 3.62-3.102c.635-.544.297-1.584-.536-1.65l-4.752-.382-1.83-4.401Z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      </span>

      {/* Label + dots */}
      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {label}
        </span>
        <Dots dotClass="h-1.5 w-1.5 text-violet-500 dark:text-violet-400" />
      </div>
    </div>
  );
}
