// Shared shapes for flag capture from the NLP modal tabs.

import type { NewNerFlag } from '../../types/generated';
import type { NerFlagKind } from '../../api/nerFlags';

// The analyzed-text context snapshotted onto every flag created in this modal.
export interface FlagContext {
  sourceText: string;
  entitySnapshot: NewNerFlag['entity_snapshot'];
  lvItemUuid: string | null;
  documentUuid: string | null;
}

// One span being flagged, prefilled by the tab that opened the dialog.
export interface FlagTarget {
  spanText: string;
  spanStart: number;
  spanEnd: number;
  sentenceText: string;
  // The involved label (the wrong one); empty for a missed entity (user supplies it).
  label: string;
  // Kinds the user may choose; a single entry hides the toggle.
  allowedKinds: NerFlagKind[];
}
