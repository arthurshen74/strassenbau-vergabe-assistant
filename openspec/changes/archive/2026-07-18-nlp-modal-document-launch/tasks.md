# Tasks: nlp-modal-document-launch

## 1. Backend: ent_html in the analyze response

- [x] 1.1 Extend `analyze_blocks` (or the service layer around it) to produce displacy `style=ent` HTML from the same per-block Docs used for entity aggregation; add `ent_html: str` to `AnalyzeResponse` in `server/shared/models/nlp_schema.py`
- [x] 1.2 Unit/integration test: analyze a text with a known rule hit and assert the occurrence appears both in `entities` and highlighted in `ent_html`; assert `ent_html` respects `include_blocks`

## 2. Backend: remove the documents listing

- [x] 2.1 Delete `GET /nlp/documents` from `server/api/routes/nlp.py`, `NlpService.list_documents`, and `NlpDocumentRead`; remove their tests
- [x] 2.2 Run backend test suite; update `export_schema` BODY_MODELS if `NlpDocumentRead` was listed

## 3. UI: source-preloaded modal

- [x] 3.1 Rework `store/nlpModal.ts`: required discriminated `NlpModalSource` union (`document` | `text`), `openNlpAnalysis(source)` mandatory argument
- [x] 3.2 Rework `NlpAnalysisDialog.tsx`: delete picker `Select`, free-text `Textarea`/Analyze button, `SourceButton` toggle, and `sourceMode`/draft state; derive queries and flag context from the store source; show the source label; keep tab behavior (LV launch still lands on Entities)
- [x] 3.3 Update the LV launch (`lvNlpPreset.tsx`, `LVItemsTable.tsx`, `LVItemDetailDialog.tsx`) to the new source shape
- [x] 3.4 Remove the sidebar "NLP Analysis" command from `components/layout/Sidebar.tsx`; keep the single `NlpAnalysisDialog` mount; delete `useNlpDocuments` from `api/nlp.ts`
- [x] 3.5 Regenerate `types/generated.ts` (`npm run gen:types`)

## 4. UI: Documents tab launch

- [x] 4.1 Add the "NLP-Analyse" row action in `views/main/ProjectDetails.tsx` for PROSE_DOCUMENT rows with completed ingest (reuse the existing per-row ingest status); wire to `openNlpAnalysis({ kind: 'document', … })`

## 5. UI: Entities tab render pane

- [x] 5.1 Render `ent_html` in `EntitiesTab.tsx` above the breakdown: `text-sm`, `max-h-[25vh]`, `overflow-y-auto`, white background, `dangerouslySetInnerHTML`; omit when no entities

## 6. Verification and docs

- [x] 6.1 Full backend suite green; `tsc` + `vite build` clean
- [x] 6.2 Browser smoke: Documents tab launch on an ingested Baubeschreibung → tabs work → Entities tab shows scrollable ent pane above breakdown; LV launch unchanged; no sidebar command
- [x] 6.3 Sweep `APPLICATION_ARCHITECTURE.md` / `AI_ARCHITECTURE.md` for mentions of the document picker or `GET /nlp/documents`; update if present
