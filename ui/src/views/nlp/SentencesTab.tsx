// Sentences tab: analysis sentences grouped by their source block, each row with
// on-demand displacy renders.

import type { AnalyzeResponse, DocumentTextRead, SentenceInfo } from '../../types/generated';
import { BlockTypeBadge } from './BlockTypeBadge';
import { SentenceRow } from './SentenceRow';

export function SentencesTab({
  analysis,
  text,
}: {
  analysis: AnalyzeResponse;
  text: DocumentTextRead;
}) {
  const blocksById = new Map(text.blocks.map((b) => [b.block_id, b]));

  const groups: { blockId: number; sentences: SentenceInfo[] }[] = [];
  for (const sentence of analysis.sentences) {
    const last = groups[groups.length - 1];
    if (last && last.blockId === sentence.block_id) {
      last.sentences.push(sentence);
    } else {
      groups.push({ blockId: sentence.block_id, sentences: [sentence] });
    }
  }

  if (groups.length === 0) {
    return <div className="py-8 text-center text-sm text-zinc-500">No sentences.</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      {groups.map((group) => {
        const block = blocksById.get(group.blockId);
        return (
          <div key={group.blockId}>
            <div className="mb-1 flex items-center gap-2">
              {block && <BlockTypeBadge type={block.block_type} />}
              <span className="text-[10px] text-zinc-400">
                block {group.blockId}
                {block ? `, p${block.page_start}` : ''}
              </span>
            </div>
            {group.sentences.map((sentence) => (
              <SentenceRow key={sentence.sentence_hash} sentence={sentence} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
