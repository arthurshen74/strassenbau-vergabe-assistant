// Open state for the NLP analysis modal. A shared store so the sidebar command
// (document-picker mode, no preset) and an LV item's "NLP-Analyse" action
// (ad-hoc text preloaded) can both open the single modal instance.

import { create } from 'zustand';

export interface NlpModalPreset {
  text: string;
  // A human label for the source (e.g. "LV OZ 01.02.0030") shown in the modal.
  sourceLabel: string;
  // Provenance links snapshotted onto any flag created from this text.
  lvItemUuid?: string | null;
  documentUuid?: string | null;
}

interface NlpModalState {
  open: boolean;
  preset: NlpModalPreset | null;
  openNlpAnalysis: (preset?: NlpModalPreset) => void;
  closeNlpAnalysis: () => void;
}

export const useNlpModalStore = create<NlpModalState>((set) => ({
  open: false,
  preset: null,
  openNlpAnalysis: (preset) => set({ open: true, preset: preset ?? null }),
  closeNlpAnalysis: () => set({ open: false, preset: null }),
}));
