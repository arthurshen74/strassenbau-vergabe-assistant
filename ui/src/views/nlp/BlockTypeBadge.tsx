import type { BlockType } from '../../api/nlp';
import { BLOCK_TYPE_BADGE, BLOCK_TYPE_LABELS } from './blockTypes';

export function BlockTypeBadge({ type }: { type: BlockType }) {
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${BLOCK_TYPE_BADGE[type]}`}
    >
      {BLOCK_TYPE_LABELS[type]}
    </span>
  );
}
