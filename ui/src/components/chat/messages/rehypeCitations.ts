// Rehype plugin that turns inline [n] / [n, m] citation tokens in the rendered Markdown
// tree into `<citation n={n}>` elements, one per number. AssistantMessage maps the
// `citation` tag to a clickable CitationBadge. Text inside code/pre is left untouched so
// bracketed numbers in code samples stay literal.

import type { Element, ElementContent, Root } from 'hast';

const CITATION_RE = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
const SKIP_TAGS = new Set(['code', 'pre']);

function citationElement(n: number): Element {
  return { type: 'element', tagName: 'citation', properties: { n }, children: [] };
}

// Returns replacement nodes for a text value, or null when it has no citation tokens.
function splitCitations(value: string): ElementContent[] | null {
  const out: ElementContent[] = [];
  let last = 0;
  let matched = false;
  for (const match of value.matchAll(CITATION_RE)) {
    matched = true;
    const start = match.index ?? 0;
    if (start > last) out.push({ type: 'text', value: value.slice(last, start) });
    const numbers = match[1]
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((x) => !Number.isNaN(x));
    for (const n of numbers) out.push(citationElement(n));
    last = start + match[0].length;
  }
  if (!matched) return null;
  if (last < value.length) out.push({ type: 'text', value: value.slice(last) });
  return out;
}

function walk(children: ElementContent[]): ElementContent[] {
  const result: ElementContent[] = [];
  for (const child of children) {
    if (child.type === 'text') {
      const parts = splitCitations(child.value);
      if (parts) result.push(...parts);
      else result.push(child);
    } else {
      if (child.type === 'element' && !SKIP_TAGS.has(child.tagName)) {
        child.children = walk(child.children);
      }
      result.push(child);
    }
  }
  return result;
}

export function rehypeCitations() {
  return (tree: Root): void => {
    tree.children = walk(tree.children as ElementContent[]);
  };
}
