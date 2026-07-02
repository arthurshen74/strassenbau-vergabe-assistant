// Katalog / recipe-author client bits. The recipe-author conversation reuses the generic
// conversation surface (prompt_type "rezept_autor") and the shared turn endpoint; its paused
// rezept_review interrupt is answered with a RezeptReviewDecision (posted as `{rezept_review}`).

import { api } from './client';
import type { ConversationRead } from '../types/generated';

const PROMPT_TYPE_REZEPT_AUTOR = 'rezept_autor';

// The reviewer's decision for a paused recipe-author run (mirrors the backend RezeptReviewDecision):
// `feedback` loops back to a redraft, `bestaetigt` persists the draft, `aktivieren` activates it.
export interface RezeptReviewDecision {
  bestaetigt: boolean;
  feedback: string | null;
  aktivieren: boolean;
}

// Launch a recipe-author conversation; the UI navigates to it and the estimator describes the recipe.
export function createRezeptAutorConversation(
  projectUuid: string | null,
): Promise<ConversationRead> {
  return api.post<ConversationRead>('/conversations', {
    prompt_type: PROMPT_TYPE_REZEPT_AUTOR,
    project_uuid: projectUuid,
    title: 'Neues Rezept',
  });
}
