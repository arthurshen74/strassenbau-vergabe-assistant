// Build the NLP-modal source for an LV item: Langtext plus Hinweis (blank-line
// separated so they analyze as distinct PROSE blocks), linked back to the item.
// GAEB text arrives with fixed-width soft wraps; those are unwrapped here so the
// Text tab, the analysis, and flag snapshots all see the same clean text.

import type { LVItem } from "../../types/generated";
import type { NlpModalSource } from "../../store/nlpModal";

// Blank lines are paragraph breaks and stay; single line breaks inside a
// paragraph are layout soft wraps. Lines join with the same German dehyphenation
// rule as reflow: a line-end hyphen joins the next line dropping the hyphen when
// it starts lowercase (justification break), keeping it when it starts uppercase
// (compound like "SRT-Pendel").
function unwrapSoftBreaks(text: string): string {
  return text
    .split(/\n\s*\n+/)
    .map((paragraph) => {
      const lines = paragraph
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line !== "");
      let joined = lines[0] ?? "";
      for (const line of lines.slice(1)) {
        if (joined.endsWith("-") && /\p{Ll}/u.test(line[0])) {
          joined = joined.slice(0, -1) + line;
        } else {
          joined = `${joined} ${line}`;
        }
      }
      return joined.replace(/ {2,}/g, " ");
    })
    .filter((paragraph) => paragraph !== "")
    .join("\n\n");
}

export function nlpSourceForLvItem(item: LVItem): NlpModalSource {
  const parts = [unwrapSoftBreaks(item.langtext)];
  if (item.hinweis) parts.push(unwrapSoftBreaks(item.hinweis));
  return {
    kind: "text",
    text: parts.join("\n\n"),
    sourceLabel: `LV OZ ${item.oz}`,
    lvItemUuid: item.lv_item_uuid,
    documentUuid: null,
  };
}
