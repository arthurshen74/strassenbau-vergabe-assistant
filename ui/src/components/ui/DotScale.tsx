// Renders a row of filled/empty dots representing a score on a fixed scale.
// Used by the eval drawer for live dimension scores and by judge run reports.

interface DotScaleProps {
  score: number | null;
  scaleMax: number;
  /** Optional accessible label — used for aria-label on the container. */
  label?: string;
}

export function DotScale({ score, scaleMax, label }: DotScaleProps) {
  if (score === null) {
    return (
      <span
        className="text-sm text-zinc-400 dark:text-zinc-500"
        aria-label={label ? `${label}: not yet scored` : 'not yet scored'}
      >
        —
      </span>
    );
  }

  return (
    <span
      className="flex items-center gap-1"
      aria-label={label ? `${label}: ${score} of ${scaleMax}` : `${score} of ${scaleMax}`}
    >
      {Array.from({ length: scaleMax }, (_, i) => (
        <span
          key={i}
          className={
            i < score
              ? 'h-2 w-2 rounded-full bg-indigo-500 dark:bg-indigo-400'
              : 'h-2 w-2 rounded-full bg-zinc-200 dark:bg-zinc-700'
          }
        />
      ))}
    </span>
  );
}
