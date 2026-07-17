// Display metadata for the NER failure taxonomy and flag kinds. AMBIGUITY is the
// one category highlighted red on the dashboard (genuinely ambiguous cases).

import type { NerFailureCategory, NerFlagKind } from '../../api/nerFlags';

export const CATEGORY_LABELS: Record<NerFailureCategory, string> = {
  register_mismatch: 'Register mismatch',
  missing_rule: 'Missing rule',
  rule_error: 'Rule error',
  tokenization: 'Tokenization',
  model_limitation: 'Model limitation',
  ambiguity: 'Ambiguity',
  other: 'Other',
};

export const CATEGORY_ORDER: NerFailureCategory[] = [
  'register_mismatch',
  'missing_rule',
  'rule_error',
  'tokenization',
  'model_limitation',
  'ambiguity',
  'other',
];

export const KIND_LABELS: Record<NerFlagKind, string> = {
  wrong_label: 'Wrong label',
  not_an_entity: 'Not an entity',
  missed_entity: 'Missed entity',
};

export function categoryLabel(category: string | null): string {
  if (category === null) return 'Un-analyzed';
  return CATEGORY_LABELS[category as NerFailureCategory] ?? category;
}
