# Design: nlp-modal-document-launch

## Flow after the change

```mermaid
flowchart LR
    subgraph launch [Launch points]
        DOCS[Project::Documents tab<br/>PROSE + ingested rows] -->|"NLP-Analyse" button| MODAL
        LV[LV item table / detail<br/>"NLP-Analyse" action] -->|Langtext + Hinweis preset| MODAL
    end
    MODAL[NLP Analysis modal<br/>source fixed at open] --> TABS[Text / Sentences / POS / Entities]
    TABS -->|document source| API1[POST /nlp/analyze document_uuid]
    TABS -->|text source| API2[POST /nlp/analyze text]
    API1 & API2 --> RESP[AnalyzeResponse<br/>sentences + pos + entities + ent_html]
    RESP --> ENT[Entities tab:<br/>ent render pane above breakdown]
```

## Decisions

### D1: The modal store carries a required, discriminated source

`nlpModal.ts` replaces `preset: NlpModalPreset | null` (null meaning "picker mode") with a required source union:

```ts
type NlpModalSource =
  | { kind: 'document'; documentUuid: string; sourceLabel: string }
  | { kind: 'text'; text: string; sourceLabel: string; lvItemUuid?: string | null; documentUuid?: string | null };
```

`openNlpAnalysis(source)` takes it as a mandatory argument. The dialog derives everything (queries, flag context, source caption) from `source.kind` — the `sourceMode` state, `documentUuid` state, `textDraft`/`analyzedText` states, and the picker/textarea/toggle UI are deleted. `sourceLabel` shows in the dialog header area for both kinds (file name or "LV OZ …").

### D2: Launch button gating in the Documents tab

The button renders only on rows with `document_type === PROSE_DOCUMENT` **and** a completed ingest (the same population `GET /nlp/documents` served: documents with extracted source lines). `ProjectDetails.tsx` already holds per-row ingest status for its Status column; the button reuses that instead of a new "analyzable" fetch. A PROSE row that is not yet ingested simply shows no button — no disabled-with-tooltip state.

### D3: `ent_html` is produced inside the analyze pass, not by a second render call

`AnalyzeResponse` gains `ent_html: str`. `analyze_blocks` already runs every included block through `nlp.pipe` as its own Doc; the ent HTML is `displacy.render(docs, style="ent")` over those same Docs (displacy accepts a Doc list and concatenates with block separators). Rationale:

- **Exact consistency.** The highlight view and the breakdown table are computed from the same Docs under the same EntityRuler state and the same `include_blocks` filter — they can never disagree.
- **No new endpoint, no cache concern.** The existing rule "ent HTML is never cached" carries over automatically because `ent_html` lives in the (client-side React Query) analyze response, which re-runs whenever include_blocks or the ruleset-dirty analyze invalidation does.
- Cost is negligible: the Docs are already in memory; rendering is string assembly.

The per-sentence `/nlp/render` endpoint is untouched (Sentences tab still uses it).

### D4: Deletion, not deprecation

`GET /nlp/documents`, `NlpDocumentRead`, `NlpService.list_documents`, `useNlpDocuments`, and the picker UI are deleted outright (repo convention: no backwards-compat shims). The sidebar "NLP Analysis" button is removed; the single `<NlpAnalysisDialog />` mount stays where it is so both launch points share one instance.

### D5: Entities tab layout

The ent render pane sits above the existing two-column breakdown: `text-sm`, `max-h-[25vh]`, `overflow-y-auto`, white background (displacy hardcodes dark-on-light colors), injected via `dangerouslySetInnerHTML` like the per-sentence renders. When the analysis finds no entities the pane is omitted (the existing empty state already covers that case).
