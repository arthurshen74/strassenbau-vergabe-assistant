// Renders streaming text content from an SSE-driven message. While the
// stream is still open we show a thin trailing caret so the user knows
// more text may arrive. The parent owns the buffer and passes it in;
// this component is a presentational view, not a stream subscriber.
//
// Why no internal subscription: SSE events for an entire conversation
// share a single connection. The view-level hook (useWorkspaceConversation
// etc.) demuxes events; making this component subscribe directly would
// duplicate that work and fight React's render model.

interface StreamingTextProps {
  text: string;
  streaming: boolean;
  className?: string;
}

export function StreamingText({ text, streaming, className }: StreamingTextProps) {
  return (
    <span
      className={className}
      aria-live={streaming ? 'polite' : undefined}
      aria-busy={streaming || undefined}
    >
      {text}
      {streaming && (
        <span
          aria-hidden
          className="ml-0.5 inline-block h-4 w-px translate-y-0.5 animate-pulse bg-zinc-400 dark:bg-zinc-500"
        />
      )}
    </span>
  );
}
