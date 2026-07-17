// Sentences tab: analysis sentences grouped by their source block, each row with
// on-demand displacy renders. Selecting text within one sentence flags a missed
// entity; block badges are shown only when document blocks are available.

import { useState } from 'react';

import type { AnalyzeResponse, DocumentTextRead, SentenceInfo } from '../../types/generated';
import { BlockTypeBadge } from './BlockTypeBadge';
import { FlagDialog } from './FlagDialog';
import { SentenceRow } from './SentenceRow';
import type { FlagContext, FlagTarget } from './flagTypes';

export function SentencesTab({
  analysis,
  text,
  context,
  labelOptions,
}: {
  analysis: AnalyzeResponse;
  text: DocumentTextRead | null;
  context: FlagContext;
  labelOptions: string[];
}) {
  const [target, setTarget] = useState<FlagTarget | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const blocksById = new Map((text?.blocks ?? []).map((b) => [b.block_id, b]));

  const groups: { blockId: number; sentences: SentenceInfo[] }[] = [];
  for (const sentence of analysis.sentences) {
    const last = groups[groups.length - 1];
    if (last && last.blockId === sentence.block_id) {
      last.sentences.push(sentence);
    } else {
      groups.push({ blockId: sentence.block_id, sentences: [sentence] });
    }
  }

  const flagMissed = (t: FlagTarget) => {
    setTarget(t);
    setDialogOpen(true);
  };

  if (groups.length === 0) {
    return <div className="py-8 text-center text-sm text-zinc-500">No sentences.</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="text-xs text-zinc-400">
        Select text within a single sentence to flag a missed entity.
      </div>
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
              <SentenceRow
                key={sentence.sentence_hash}
                sentence={sentence}
                onFlagMissed={flagMissed}
              />
            ))}
          </div>
        );
      })}

      <FlagDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        target={target}
        context={context}
        labelOptions={labelOptions}
      />
    </div>
  );
}
