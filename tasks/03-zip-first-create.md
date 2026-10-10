# Task 03: Recursive ZIP expansion and ZIP-first project creation

Depends on: 01 (a ZIP with two GAEB files must not trigger the old LV replace).
Parallel with 02, 04. Task 05 adds one call into the service method you create here.

## Use a worktree

Work in a dedicated git worktree and branch, never in the main checkout:

```bash
git worktree add ../swa-task03 -b task/03-zip-first-create
```

Follow the "Worktree setup" section of `tasks/README.md` for the rest: per-worktree
`uv sync` and `npm ci`, your own test database (`POSTGRES_DB=roadbuilders_t03`
for pytest), one shared compose stack that you never start or restart, migrations
verified on a scratch database only, and no commits unless asked.

## Goal

`POST /projects/from-zip` takes one ZIP, creates a project named after the ZIP, expands
the ZIP recursively, stores and enqueues every `.pdf`, `.x83`, `.d83` as a document (GAEB
files as LV documents, PDFs as prose) and returns the project with its documents. The UI
gets an "Ingest Project from ZIP" entry next to "Ingest New Project".

The existing form flow and `POST /projects/{p}/documents` stay unchanged in behaviour,
except that nested ZIPs inside an uploaded ZIP are now expanded there too.

## Current state

- `server/shared/services/project_service.py`: `ingest_documents(project_uuid, uploads)`
  expands `.zip` uploads with `_expand_zip` (one level, flattens to basename, drops dot
  files and `__MACOSX`), classifies by filename (`_classify_document_type`), stores the
  blob under `raw/{document_uuid}`, inserts the `Document`, enqueues an `IngestJob`.
- `ProjectCreate` requires only `project_name`; `NewProject` defaults everything else to
  None (header fields are filled later by task 05).
- Route file: `server/api/routes/projects.py`; service DI helpers at the top of it.
- UI: `ui/src/views/main/ProjectsView.tsx` has `View = list | create | detail` and an
  "Ingest New Project" button; uploads use raw `fetch` + `FormData` (see `postDocuments` in
  `ui/src/api/projects.ts`).

## Changes

### ZIP expansion (`project_service.py`)
- Replace `_expand_zip(data)` with `expand_zip(data, *, allowed_suffixes: frozenset[str] |
  None = None) -> ZipExpansion` where `ZipExpansion` is a frozen dataclass with
  `uploads: list[UploadInput]` and `skipped: list[str]` (entry paths that were dropped
  and why is not needed, the path is enough).
- Recursive: an entry whose name ends in `.zip` (case-insensitive) is opened in memory and
  expanded with the same rules. Constants at module level: `ZIP_MAX_DEPTH = 5`,
  `ZIP_MAX_ENTRIES = 1000`, `ZIP_MAX_TOTAL_BYTES = 2 * 1024**3`. Count uncompressed bytes
  via `ZipInfo.file_size` before reading; exceeding any cap raises `ZipTooLargeError`
  (new exception in the module) which the route maps to 413. A corrupt nested zip
  (`zipfile.BadZipFile`) is skipped and recorded in `skipped`, not fatal.
- Filtering: when `allowed_suffixes` is given, entries with other suffixes go to `skipped`.
  The from-zip flow passes `INGESTIBLE_SUFFIXES = frozenset({".pdf", ".x83", ".d83"})`
  (reuse the GAEB suffix knowledge from `shared.services.ingestion.gaeb.is_gaeb_lv_file`
  rather than retyping `.x83`/`.d83` if a constant exists there; otherwise define the set
  once next to `is_gaeb_lv_file` and import it). The existing upload flow passes None
  (unchanged behaviour: everything non-junk is ingested).
- Name collisions: keep the basename; if a basename repeats within one expansion, prefix
  the later ones with their nearest parent directory name joined by `__`
  (`Los2__LV.pdf`); if still colliding, append `-2`, `-3`. Entries from nested zips use
  the nested zip's stem as the parent directory for this purpose.
- Content type: keep `mimetypes.guess_type` with the octet-stream default.

### Service: create from ZIP
- `ProjectService.create_from_zip(file_name: str, data: bytes) -> ProjectFromZipResult`.
  Steps: project name = `PurePosixPath(file_name).stem` (fallback `"Projekt"` if empty);
  `projects.add(NewProject(project_name=...))`; `expansion = expand_zip(data,
  allowed_suffixes=INGESTIBLE_SUFFIXES)`; store + record + enqueue each upload through
  the existing per-upload path (factor the body of the current per-upload branch so both
  flows share it; no second copy of the store/insert/enqueue sequence); return the result.
- `ProjectFromZipResult` (Pydantic, `extra="forbid"`, in `shared/models/project_schema.py`):
  `project: ProjectRead`, `documents: list[DocumentRead]`, `skipped: list[str]`.
- Leave a clearly named seam for task 05: after enqueuing the documents, call
  `self._after_zip_ingest(project_uuid)` which is a no-op method with a docstring saying
  task 05 enqueues the project-info job here. (Task 05 replaces the no-op; do not try to
  implement it.)

### Route
- `POST /projects/from-zip` (multipart, field `file`, must end in `.zip` else 422),
  status 201, `response_model=ProjectFromZipResult`, uses
  `get_writable_project_service`. `ZipTooLargeError` -> 413 with a message naming the
  cap hit. Register it before the `/{project_uuid}` routes so FastAPI does not try to
  parse `from-zip` as a UUID (or rely on the UUID type mismatch; be explicit, put it first).
- Request size: check whether the API has a body-size limit middleware; if not, note the
  reverse-proxy expectation in `DEVOPS.md` rather than adding one here.

### UI
- `ui/src/api/projects.ts`: `useCreateProjectFromZip()` mutation posting `FormData` to
  `/projects/from-zip` (same error handling as `postDocuments`), returning
  `ProjectFromZipResult`, invalidating `projectKeys.all`.
- `ui/src/views/main/CreateProjectFromZipDialog.tsx`: file input accepting `.zip`, shows the
  chosen file name and size, a submit button "Create and ingest", an error line. On
  success close and call `onCreated(result)`.
- `ProjectsView.tsx`: second button "Ingest Project from ZIP" next to "Ingest New Project";
  on success navigate to `{ mode: 'detail', id }`. If `result.skipped` is non-empty, show a
  dismissible note on the project page listing the skipped entries (keep it in local state
  passed through the view; no store).
- The project page already streams per-document ingest status, so progress is visible as
  soon as the detail view opens.

### Tests
- Unit (`tests/unit/services/test_project_service.py`): nested zip two levels deep is
  flattened; depth cap triggers; entry cap triggers; total-bytes cap triggers (build the
  zip with a large `file_size` by writing real bytes, keep it small by lowering the cap via
  monkeypatch); suffix filter populates `skipped`; basename collision renaming; corrupt
  nested zip is skipped not raised; project name from zip stem.
- API (`tests/integration/api/test_projects_api.py`): post a small in-memory zip with one
  PDF, one X83, one nested zip holding a D83 and a `.txt`; assert 201, three documents
  (two LV, one prose), `skipped == ["<nested>/notes.txt"]`-style entry, three queued
  ingest jobs. Override `get_storage` with a fake that records `put_object` calls.
- A `.docx` upload returns 422; a 1-byte `.zip` that is not a zip returns 422.

### Docs
- `README.md` "First project": describe both ways to create a project.
- `APPLICATION_ARCHITECTURE.md`: the upload/ingest sequence gains the from-zip entry
  point.
- `DEVOPS.md`: the ZIP caps as constants and where to raise them.

## Done when
- A real tender ZIP (nested zips, mixed files) creates a project whose Documents tab lists
  every PDF and GAEB file as queued, with two GAEB files coexisting as LV documents.
- The old form + upload flow is unchanged apart from nested-zip support.
- Tests and types are green; the no-op seam for task 05 exists.
