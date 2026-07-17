// Build the NLP-modal source for an LV item: Langtext plus Hinweis (blank-line
// separated so they analyze as distinct PROSE blocks), linked back to the item.

import type { LVItem } from "../../types/generated";
import type { NlpModalSource } from "../../store/nlpModal";

export function nlpSourceForLvItem(item: LVItem): NlpModalSource {
  const parts = [item.langtext];
  if (item.hinweis) parts.push(item.hinweis);
  return {
    kind: "text",
    text: parts.join("\n\n"),
    sourceLabel: `LV OZ ${item.oz}`,
    lvItemUuid: item.lv_item_uuid,
    documentUuid: null,
  };
}
