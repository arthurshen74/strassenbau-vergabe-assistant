// Classify a project document by its filename. A GAEB exchange file (.d83 or .x83) is the
// Leistungsverzeichnis by definition; everything else — including the LV print-layout
// PDF — is prose. Mirrors _classify_document_type in server/shared/services/project_service.py.

import type { DocumentRead } from '../types/generated';

export type DocumentType = DocumentRead['document_type'];

export const DOCUMENT_TYPE_LV = 'LV_DOCUMENT' satisfies DocumentType;
export const DOCUMENT_TYPE_PROSE = 'PROSE_DOCUMENT' satisfies DocumentType;

// A GAEB exchange file (fixed-format GAEB 90 .d83 or GAEB DA XML .x83) is always the LV.
export const GAEB_LV_PATTERN = /\.(d83|x83)$/i;

export function classifyDocumentType(fileName: string): DocumentType {
  return GAEB_LV_PATTERN.test(fileName) ? DOCUMENT_TYPE_LV : DOCUMENT_TYPE_PROSE;
}
