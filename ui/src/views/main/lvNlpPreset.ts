// Build the NLP-modal preset for an LV item: Langtext plus Hinweis (blank-line
// separated so they analyze as distinct PROSE blocks), linked back to the item.

import type { LVItem } from '../../types/generated';
import type { NlpModalPreset } from '../../store/nlpModal';

export function nlpPresetForLvItem(item: LVItem): NlpModalPreset {
  const parts = [item.langtext];
  if (item.hinweis) parts.push(item.hinweis);
  return {
    text: parts.join('\n\n'),
    sourceLabel: `LV OZ ${item.oz}`,
    lvItemUuid: item.lv_item_uuid,
    documentUuid: null,
  };
}
