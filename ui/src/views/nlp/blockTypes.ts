// Shared block-type presentation for the NLP modal: label, badge styling, and
// which types are selectable for analysis (furniture never is).

import type { BlockType } from '../../api/nlp';

export const SELECTABLE_BLOCK_TYPES: BlockType[] = [
  'prose',
  'heading',
  'list_item',
  'table',
  'caption',
  'footnote',
];

export const DEFAULT_INCLUDE_BLOCKS: BlockType[] = ['prose', 'heading', 'list_item'];

export const BLOCK_TYPE_LABELS: Record<BlockType, string> = {
  prose: 'Prose',
  heading: 'Heading',
  list_item: 'List item',
  table: 'Table',
  caption: 'Caption',
  footnote: 'Footnote',
  furniture: 'Furniture',
};

export const BLOCK_TYPE_BADGE: Record<BlockType, string> = {
  prose: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  heading: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
  list_item: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
  table: 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300',
  caption: 'bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-300',
  footnote: 'bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-300',
  furniture: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
};
