// Open state for the NLP analysis modal. A shared store so both launch points —
// a Baubeschreibung's "NLP-Analyse" action in the Documents tab (a document source)
// and an LV item's "NLP-Analyse" action (ad-hoc text) — open the single modal
// instance with its source fixed at open. There is no in-modal source selection.

import { create } from "zustand";

export type NlpModalSource =
  | { kind: "document"; documentUuid: string; sourceLabel: string }
  | {
      kind: "text";
      text: string;
      // A human label for the source (e.g. "LV OZ 01.02.0030") shown in the modal.
      sourceLabel: string;
      // Provenance links snapshotted onto any flag created from this text.
      lvItemUuid?: string | null;
      documentUuid?: string | null;
    };

interface NlpModalState {
  open: boolean;
  source: NlpModalSource | null;
  openNlpAnalysis: (source: NlpModalSource) => void;
  closeNlpAnalysis: () => void;
}

export const useNlpModalStore = create<NlpModalState>((set) => ({
  open: false,
  source: null,
  openNlpAnalysis: (source) => set({ open: true, source }),
  closeNlpAnalysis: () => set({ open: false, source: null }),
}));
