// Classify a project document by its filename. An LV document (Leistungsverzeichnis)
// follows a fixed naming convention (<name>_LV<suffix>.pdf); everything else is prose.

import type { DocumentRead } from '../types/generated';

export type DocumentType = DocumentRead['document_type'];

export const DOCUMENT_TYPE_LV = 'LV_DOCUMENT' satisfies DocumentType;
export const DOCUMENT_TYPE_PROSE = 'PROSE_DOCUMENT' satisfies DocumentType;

// A single PDF named like "<name>_LV<x>.pdf" is the Leistungsverzeichnis.
export const LV_FILENAME_PATTERN = /^[a-zA-Z0-9_]+_LV[a-zA-Z0-9]*\.pdf$/;

export function classifyDocumentType(fileName: string): DocumentType {
  return LV_FILENAME_PATTERN.test(fileName) ? DOCUMENT_TYPE_LV : DOCUMENT_TYPE_PROSE;
}
