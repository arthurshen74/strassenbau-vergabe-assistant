# Task 01: Several LV documents per project (backend)

Depends on: nothing. Blocks: 02, 03.

## Use a worktree

Preflight: this task has no dependencies; branch from the current `main`.

Work in a dedicated git worktree and branch, never in the main checkout:

```bash
git worktree add ../swa-task01 -b task/01-multi-lv-backend
```

Follow the "Worktree setup" section of `tasks/README.md` for the rest: per-worktree
`uv sync` and `npm ci`, your own test database (`POSTGRES_DB=roadbuilders_t01`
for pytest), one shared compose stack that you never start or restart, migrations
verified on a scratch database only, and no commits unless asked.

## Goal

A project may hold any number of GAEB LV documents. Each keeps its own LV items, LV texts
and ES chunks (already keyed by `document_uuid`). Uploading a GAEB file adds a new LV
document instead of replacing the existing one. Every read that assumed "the" LV document
either takes a `document_uuid` or works across all LV documents of the project.

## Where the one-LV assumption lives today

1. `server/shared/db/tables/documents.py`: partial unique index
   `uq_one_lv_document_per_project` (`project_uuid` where `document_type = 'LV_DOCUMENT'`).
2. `server/shared/repositories/documents.py::get_lv_document` (docstring says "single").
3. `server/shared/services/project_service.py::_ingest_one`: a GAEB upload deletes the
   existing LV document first (module docstring describes this too).
4. `server/shared/services/retrieval/service.py::_resolve_scope`: PLUS looks up the LV
   document and raises `RetrievalError` without one; `plus_filter` takes
   `lv_document_uuid` to exclude that document's own DOCUMENT chunks;
   `_thumbnail_document_uuid` resolves LV_ITEM thumbnails to the LV document;
   `ScopeTrace.lv_document_uuid`.
5. `server/shared/services/project_chat_agent.py::_retrieve`: catches `RetrievalError` to
   fall back to SIMPLE. `get_lv_single_item(oz)` uses `get_by_project_and_oz`, which
   returns one row; with several LVs an OZ can match several positions.
6. `LVItemRepository.list_by_project` / `LVTextRepository.list_by_project`: join on
   `document_type = LV_DOCUMENT`, so they already span all LV documents, but order only by
   `oz` / `sequence`, which interleaves documents.
7. `GET /projects/{p}/lv-items` and `/lv-texts` routes and `ProjectService.list_lv_items` /
   `list_lv_texts`.

## Changes

### Schema
- Remove the partial unique index from `documents.py`.
- `sql/18_multi_lv_documents.sql`: `DROP INDEX IF EXISTS uq_one_lv_document_per_project;`
  with the standard header. Apply to the dev DB after verifying on a scratch DB.

### Repositories
- `DocumentRepository`: replace `get_lv_document` with
  `list_lv_documents(project_uuid) -> list[Document]` ordered by `created_at`. Delete the
  old method and fix every caller (grep `get_lv_document` in `server/` and `tests/`).
- `LVItemRepository`: add `list_by_document(document_uuid) -> list[LVItem]` ordered by `oz`
  if it does not exist (check first; `LVTextRepository.list_by_document` already exists).
  Change `list_by_project` ordering to `(documents.created_at, lv_items.oz)` so one
  document's positions stay together. Same for `LVTextRepository.list_by_project`:
  `(documents.created_at, sequence)`.
- `LVItemRepository.get_by_project_and_oz`: keep the signature but document that it returns
  the first match in document order, and add `list_by_project_and_oz(project_uuid, oz) ->
  list[LVItem]` for callers that must see all matches.

### Upload path
- `ProjectService._ingest_one`: delete the "supersede existing LV" block. A GAEB upload
  always creates a new LV document. Update the module docstring and the docstring of the
  upload route (`upload_documents` in `server/api/routes/projects.py`) and of
  `useUploadDocuments` / `UploadDocumentDialog` copy in the UI (task 02 owns the UI text,
  but the backend docstrings are yours).
- `get_deletable_project_service` was injected into the upload route only because of the
  replace path. Switch the upload route back to `get_writable_project_service` if nothing
  else in `ingest_documents` needs thumbnails/search/lv repos (verify by reading the method).

### Retrieval
- `plus_filter(project_uuid)`: drop the `lv_document_uuid` parameter and the `must_not`
  branch. GAEB documents produce no DOCUMENT chunks (see `IngestionService.
  _ingest_gaeb_document`), so the exclusion was already a no-op. The filter becomes
  `project_uuid` AND `source_doc_type IN (DOCUMENT, LV_ITEM, LV_TEXT)`.
- `RetrievalService._resolve_scope`: PLUS no longer needs a document lookup and no longer
  raises. Remove `RetrievalError` if nothing else raises it (grep), and remove the fallback
  branch in `project_chat_agent._retrieve`. Remove `lv_document_uuid` from `ScopeTrace`
  (it is in the exported schema, so regenerate types; grep the UI for `lv_document_uuid`).
- `_thumbnail_document_uuid` / `_thumbnail_ref`: first verify whether GAEB-parsed LV items
  ever carry pages (`grep -n pages server/shared/services/ingestion/gaeb/ -r` and
  `lv/types.py`). If they never do, LV_ITEM / LV_TEXT chunks have no thumbnail: delete the
  LV special case and return a `ThumbnailRef` only for DOCUMENT chunks. If they can, resolve
  the thumbnail document through the item's own `document_uuid` instead of a project-wide
  lookup.
- Update `tests/unit/search/test_footprint_query.py` and any retrieval unit tests that build
  `plus_filter(project_uuid, lv_document_uuid)`.

### Chat agent and aggregate LV
- `get_lv_all`: group the output by LV document with a header line carrying the file name
  (needs `DocumentRepository.list_lv_documents` + per-document listing). Keep the artifact
  shape (`RESULT_LV_ITEMS`) but add `document_uuid` and `file_name` per item if the dumper
  does not already include them.
- `get_lv_single_item(oz)`: use `list_by_project_and_oz`; if several match, list all with
  their file names.
- `aggregate_lv.py`: no behaviour change required; it already works over all items. Add a
  one-line comment that it spans every LV document of the project.

### API
- Keep `GET /projects/{p}/lv-items` and `/lv-texts` (project-wide, document order).
- Add `GET /projects/{p}/documents/{d}/lv-items` and `/lv-texts` (404 when the document
  is not in the project; empty list for a prose document). Service methods
  `list_document_lv_items` / `list_document_lv_texts`.
- Run `npm run gen:types` at the end (ScopeTrace change, new routes do not add types but
  keep the schema in sync).

### Tests
- `tests/unit/services/test_project_service.py::test_gaeb_upload_replaces_existing_lv_document`
  becomes `test_gaeb_upload_adds_second_lv_document` (nothing deleted, two LV documents).
- `tests/integration/repositories/test_documents.py`: two LV documents in one project
  insert fine; `list_lv_documents` order.
- `tests/integration/api/test_projects_lv_items.py`: extend with two LV documents and the
  per-document routes.
- Retrieval unit tests for the new `plus_filter`.

### Docs
- `AI_ARCHITECTURE.md`: three mentions of "the LV document" (Plus modality description,
  ingestion overview). Make them plural and state that PLUS spans all LV documents.
- `APPLICATION_ARCHITECTURE.md`: the ERD/notes if they mention the one-LV constraint;
  the `documents` entity.
- `GLOSSARY.md`: under LV, note that a project can carry several LV files (e.g. the same LV
  as X83 and D83, or one per Los).

## Done when
- A project accepts two GAEB uploads and both show up as LV documents with their own items
  and texts; deleting one leaves the other intact (Postgres cascade + ES footprint).
- PLUS retrieval works on a project with zero, one or several LV documents.
- All listed tests pass; types regenerated; docs updated.
