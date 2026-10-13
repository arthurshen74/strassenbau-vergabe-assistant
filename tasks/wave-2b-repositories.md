# Wave 2B — Repositories + Unit of Work

Read `tasks/README.md` first (shared setup + conventions). The domain models
(`server/shared/models/`) and Core tables (`server/shared/db/tables/`) already exist and are tested —
**reuse them, do not redefine.** `DATA_ARCHITECTURE.md` §5 (repository pattern) and §6 (Unit of Work)
are the canonical templates; the `LVItemRepository` is written out almost verbatim there.

## Goal

One repository per aggregate under `server/shared/repositories/`, each constructed with an
`AsyncConnection`, plus a Unit of Work in `server/shared/db/unit_of_work.py`, plus an integration test
per repository under `tests/integration/repositories/`.

These can be split across agents (one per repository). The Unit of Work is the join point — do it last.

## Repository pattern (apply to all)

```python
class XRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn
    # add() -> returning(table) -> Model.model_validate(dict(row))
    # get()/list() -> select(...).mappings().first()/.all()
```

Translate rows with `(...).mappings()` + `Model.model_validate(dict(row))`. Inserts use
`.returning(<table>)`. Never accept the engine. Each method fully type-annotated.

## Repositories to build

1. **`repositories/projects.py` → `ProjectRepository`**
   `add(NewProject)`, `get(uuid)`, `list()`, `update(uuid, **changes)`, `delete(uuid)`.
   No `(vergabestelle, vergabe_id)` unique exists in the schema — do **not** add a `get_by_external_id`.

2. **`repositories/documents.py` → `DocumentRepository`**
   `add(NewDocument)`, `get(uuid)`, `list_by_project(project_uuid)`, `delete(uuid)`, and
   **`get_lv_document(project_uuid) -> Document | None`** (filters `document_type == LV_DOCUMENT`;
   backs the RETRIEVAL "Plus" filter and the LV-item chat gate). Use `DocumentType.LV_DOCUMENT`, not a
   literal.

3. **`repositories/source_lines.py` → `SourceLineRepository`**
   `add_many(list[NewSourceLine])` (bulk insert), `list_by_document(document_uuid)` ordered by
   `line_id`. Upsert on the `(document_uuid, line_id)` natural key (re-ingestion replays SourceLines).

4. **`repositories/thumbnails.py` → `ThumbnailRepository`**
   `add(NewThumbnail)`, `list_by_document(document_uuid)` ordered by `page_number`.

5. **`repositories/ingest_jobs.py` → `IngestJobRepository`**
   `add(NewIngestJob)` (defaults to `QUEUED`), `get(uuid)`, `set_status(uuid, IngestStatus)`, and
   **`claim_next() -> IngestJob | None`** using `SELECT ... FOR UPDATE SKIP LOCKED` then transition to
   `RUNNING` (see the `SELECT ... SKIP LOCKED` note in `DATA_SCHEMA.md`).
   **`repositories/ingest_job_events.py` → `IngestJobEventRepository`**: `add(NewIngestJobEvent)`,
   `list_for_job(job_uuid)` ordered by `ts`.

6. **`repositories/lv_items.py` → `LVItemRepository`**
   Copy `DATA_ARCHITECTURE.md` §5 verbatim (adjust imports to `shared.*`): `get`,
   **`get_by_project_and_oz`** (joins `documents` on `document_type == LV_DOCUMENT` — the
   `LV_Item_Lookup` chat gate), **`list_by_parent_oz`** (the `List_LV_Items_by_Parent_OZ` gate), `add`,
   `add_many`. The `(document_uuid, oz)` unique already exists.

7. **`repositories/prompt_versions.py` → `PromptVersionRepository`**
   Immutable versions. `add(NewPromptVersion)` **auto-assigns the next `version` per `prompt_type`**
   (`SELECT max(version)+1 ... WHERE prompt_type = :t`, or a per-type sequence; guard the
   `(prompt_type, version)` unique under concurrency), `get_by_type_and_version(prompt_type, version)`,
   `get_latest(prompt_type)`, `list_by_type(prompt_type)`. `initial_messages` round-trips through JSONB
   as a list of `ChatMessage` dicts.

## Unit of Work — `server/shared/db/unit_of_work.py`

Per `DATA_ARCHITECTURE.md` §6: `UnitOfWork(conn)` exposes every repository sharing one connection;
`unit_of_work(engine)` async context manager wraps `engine.begin()` (commit on success, rollback on
exception). Then **wire `server/api/deps.py:get_uow`** to yield a `UnitOfWork` instead of a bare
`AsyncConnection` (it currently yields the raw connection — update it and keep `get_connection`
read-only).

## Verification

- Per-repo integration test in `tests/integration/repositories/test_<entity>.py` using the `conn`
  fixture (rollback-per-test). Cover: add→get round-trip, list ordering, update/delete where present,
  and the key invariants — `DocumentRepository` the partial-unique "second LV doc raises
  `IntegrityError`"; `LVItemRepository` both gate methods resolve through the LV document;
  `PromptVersionRepository` version auto-increment + `(prompt_type, version)` uniqueness + JSONB
  round-trip; `IngestJobRepository` `claim_next` returns one then `None`.
- A `tests/integration/db/test_unit_of_work.py`: a multi-repo write commits atomically; an exception
  rolls everything back.
- Run: `docker compose up -d postgres && (cd server && python -m scripts.bootstrap_dbs) && pytest tests/integration/repositories tests/integration/db -q`.

## Done when

All repositories + UoW exist, `get_uow` yields a `UnitOfWork`, and the integration suite is green.
