// Document type and form-role vocabulary as the server assigns them. The type is decided
// server-side at upload (a fillable PDF form is detected from its bytes), so the UI only
// labels what it reads from DocumentRead.

import type { DocumentRead } from '../types/generated';

export type DocumentType = DocumentRead['document_type'];
export type FormRole = NonNullable<DocumentRead['form_role']>;

export const DOCUMENT_TYPE_LV = 'LV_DOCUMENT' satisfies DocumentType;
export const DOCUMENT_TYPE_PROSE = 'PROSE_DOCUMENT' satisfies DocumentType;
export const DOCUMENT_TYPE_FORM = 'FORM_DOCUMENT' satisfies DocumentType;

// A GAEB exchange file (fixed-format GAEB 90 .d83 or GAEB DA XML .x83) is always an LV document.
export const GAEB_LV_PATTERN = /\.(d83|x83)$/i;

const DOCUMENT_TYPE_SUFFIX = '_DOCUMENT';

export const DOCUMENT_TYPE_COLOR: Record<DocumentType, 'amber' | 'indigo' | 'zinc'> = {
  LV_DOCUMENT: 'amber',
  FORM_DOCUMENT: 'indigo',
  PROSE_DOCUMENT: 'zinc',
};

// Badge text: the type without its _DOCUMENT suffix (LV, FORM, PROSE).
export function documentTypeLabel(type: DocumentType): string {
  return type.replace(DOCUMENT_TYPE_SUFFIX, '');
}

const FORM_ROLE_LABEL: Record<FormRole, string> = {
  vergabestelle: 'Vergabestelle',
  bieter: 'Bieter',
  unbekannt: 'Rolle unbekannt',
};

export function formRoleLabel(role: FormRole): string {
  return FORM_ROLE_LABEL[role];
}

// "FB 312-B · Vergabestelle"; a form without a Formblatt id is just "Formblatt".
export function formSummary(formId: string | null | undefined, role: FormRole): string {
  return `${formId ?? 'Formblatt'} · ${formRoleLabel(role)}`;
}
