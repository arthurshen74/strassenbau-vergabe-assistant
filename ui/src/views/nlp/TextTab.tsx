// Text tab: reflowed blocks, with a toggle to the original source lines where
// furniture and non-included block types render dimmed with their classification.

import { useState } from 'react';

import type { BlockType } from '../../api/nlp';
import { Switch, SwitchField } from '../../components/ui/switch';
import { Label } from '../../components/ui/fieldset';
import type { DocumentTextRead } from '../../types/generated';
import { BlockTypeBadge } from './BlockTypeBadge';

export function TextTab({
  text,
  includeBlocks,
}: {
  text: DocumentTextRead;
  includeBlocks: BlockType[];
}) {
  const [showOriginal, setShowOriginal] = useState(false);

  return (
    <div className="flex flex-col gap-3">
      <SwitchField className="self-end">
        <Label className="text-xs">Original lines</Label>
        <Switch checked={showOriginal} onChange={setShowOriginal} />
      </SwitchField>

      {showOriginal ? (
        <div className="flex flex-col font-mono text-xs">
          {text.lines.map((line) => {
            const excluded =
              line.block_type === 'furniture' || !includeBlocks.includes(line.block_type);
            return (
              <div
                key={line.line_id}
                className={`flex items-baseline gap-2 border-b border-zinc-100 py-0.5 dark:border-zinc-800 ${
                  excluded ? 'opacity-40' : ''
                }`}
              >
                <span className="w-14 shrink-0 text-right text-zinc-400">
                  {line.page}:{line.line_id}
                </span>
                <span className="w-20 shrink-0">
                  <BlockTypeBadge type={line.block_type} />
                </span>
                <span className="whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">
                  {line.text}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {text.blocks.map((block) => {
            const excluded = !includeBlocks.includes(block.block_type);
            return (
              <div key={block.block_id} className={excluded ? 'opacity-40' : ''}>
                <div className="mb-0.5 flex items-center gap-2">
                  <BlockTypeBadge type={block.block_type} />
                  <span className="text-[10px] text-zinc-400">
                    p{block.page_start}
                    {block.page_end !== block.page_start ? `–${block.page_end}` : ''}
                  </span>
                </div>
                <p
                  className={`text-sm text-zinc-800 dark:text-zinc-200 ${
                    block.block_type === 'heading' ? 'font-semibold' : ''
                  }`}
                >
                  {block.text}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
