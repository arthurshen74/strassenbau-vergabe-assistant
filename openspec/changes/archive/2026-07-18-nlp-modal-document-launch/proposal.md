# Proposal: nlp-modal-document-launch

## Why

The NLP Analysis modal currently owns its own source selection: a document picker (backed by `GET /nlp/documents`) and a Document/Free-text toggle with a paste textarea. In practice the modal is always reached *from* something — a Baubeschreibung or an LV item — so the in-modal selection is redundant UI that also forces a "no source yet" empty state. Additionally, the Entities tab shows the aggregated label/occurrence breakdown but never the entities *in context*; the displacy ent highlight view exists only per-sentence in the Sentences tab.

## What Changes

1. **Launch from the Project Documents tab.** Each PROSE_DOCUMENT row whose ingest has produced source lines gets an "NLP-Analyse" launch action (same pattern as LV items). Clicking it opens the modal with that document as the source. LV_DOCUMENT rows and un-ingested documents get no button.
2. **The modal loses source selection entirely.** No document picker, no Document/Free-text toggle, no paste textarea. The modal always opens preloaded with exactly one source: a document (from the Documents tab) or ad-hoc text (from an LV item's "NLP-Analyse" action). The sidebar "NLP Analysis" command is removed — with no in-modal source selection there is nothing a bare launch could show.
3. **Entities tab gains a full-text ent render.** The displacy `style=ent` HTML for the whole analyzed text (included blocks only, same EntityRuler state as the breakdown) renders above the existing label/occurrence report, in a `text-sm` container capped at `max-h-[25vh]` with a vertical scrollbar on overflow.

Deletions that follow: `GET /nlp/documents` (+ `NlpDocumentRead`, service method, `useNlpDocuments`, picker `Select`) — its only consumer was the picker; the Documents tab already has every row's uuid and type.

Out of scope: the Sentences tab is unchanged (per-sentence dep/ent buttons and missed-entity selection flagging stay as they are). The ad-hoc text API path (`AnalyzeRequest.text`) is unchanged — the LV launch continues to use it.

## Capabilities

### Modified

- **`nlp-analysis-modal`** — the picker/free-text requirement is replaced by a preloaded-source requirement (document via Documents-tab launch, text via LV launch).
- **`nlp-analysis-api`** — the "Analyzable documents can be listed" requirement is removed with the endpoint.
- **`nlp-entities-tab`** — the analyze response additionally carries the full-text ent HTML; the Entities tab shows it above the breakdown.

### Added

(none — all changes land in existing capabilities)

## Impact

- Backend: `server/api/routes/nlp.py` (drop `/documents` route), `server/shared/services/nlp/service.py` (drop `list_documents`), `server/shared/services/nlp/analysis.py` (produce ent HTML in the analyze pass), `server/shared/models/nlp_schema.py` (`AnalyzeResponse.ent_html`, drop `NlpDocumentRead`).
- UI: `views/nlp/NlpAnalysisDialog.tsx` (remove picker/toggle/textarea), `store/nlpModal.ts` (source becomes required), `views/main/ProjectDetails.tsx` (launch button), `views/nlp/EntitiesTab.tsx` (ent render pane), `components/layout/Sidebar.tsx` (remove command), `api/nlp.ts` (drop `useNlpDocuments`), regenerated `types/generated.ts`.
- No DB or prompt changes. No new endpoints.
