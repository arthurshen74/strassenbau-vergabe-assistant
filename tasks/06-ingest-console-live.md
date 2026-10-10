# Task 06: Live ingest console

Depends on: 05 (project-info job and worker loop) merged on main, plus the uncommitted
`sql/22_rag_query_vergabestelle.sql` follow-up committed, so `sql/23` is the next free
migration number.

## Use a worktree

Preflight, on `main` before creating the worktree:

```bash
test -f sql/20_project_info_jobs.sql && test -f sql/22_rag_query_vergabestelle.sql \
  && test -f server/worker/project_info_loop.py   # 05 + vergabestelle follow-up merged
```

```bash
git worktree add ../swa-task06 -b task/06-ingest-console-live
```

Follow the "Worktree setup" section of `tasks/README.md` (own `uv sync` / `npm ci`, test DB
`POSTGRES_DB=roadbuilders_t06`, never touch the compose stack, migrations on a scratch DB,
no commits).

## Goal

After a user submits files for ingestion, they land in the ingest console without doing
anything. The console shows what is happening now: active jobs by default, the
project-info job next to the document jobs, and the current step of every job inline.
It updates by itself when the data changes. The Refresh button goes away.

## Current state (read before changing)

- `ui/src/views/main/IngestConsoleView.tsx`: table of ingest jobs, status filter defaults
  to "All", Refresh button, "Activity" opens `IngestActivityTerminal` (SSE tail of one
  job).
- `ui/src/api/ingestJobs.ts::useIngestJobs`: React Query polling (2.5 s while active,
  8 s idle). New jobs can take up to 8 s to appear, which is why it feels like it needs a
  manual refresh.
- `server/api/routes/ingest_jobs.py`: `GET /ingest-jobs`, `POST /{job}/requeue`,
  `GET /{job}/activity/stream`.
- `server/shared/services/ingest_admin.py::stream_job_activity` and
  `server/shared/services/ingestion/status_stream.py::stream_project_status` already
  implement "poll the DB server-side, emit SSE only on change" (there is no
  LISTEN/NOTIFY). This task reuses that pattern for the job list.
- Two progress streams exist for document jobs: `ingest_job_events` (coarse milestones,
  drives the project status bar) and `ingestion_activity_log` (granular lines, buffered by
  `ActivityWriter`, each flush also refreshes the lease). The project-info job has
  neither: it only logs to stdout.
- The console is opened only from the sidebar (`Sidebar.tsx`, main-window kind
  `ingest_console`).
- Upload entry points: `UploadDocumentDialog` (project page, closes on success) and
  `CreateProjectFromZipDialog` (projects list, `onCreated` goes to the project detail
  with the `skipped` note).

## Decisions

1. **Live updates via a server-side diffed SSE stream, not client polling.** A new
   `GET /ingest-jobs/stream` holds one connection, re-runs the console query every
   `settings.ingest_status_poll_interval_seconds` (1.5 s) on the server and emits a full
   snapshot only when the result changed. The UI writes the snapshot into the React Query
   cache with `setQueryData`; the query itself has no `refetchInterval`. This matches the
   two existing streams. LISTEN/NOTIFY is out of scope: it needs a dedicated listener
   connection per API process and fan-out, for a gain of ~1 s latency.
2. **One console row type with a discriminator.** `ConsoleJobKind(StrEnum)`:
   `ingest`, `project_info`. The project-info row has no document, so `document_uuid` and
   `file_name` are null for it and the File column shows "Projektinfo".
3. **Project-info activity gets its own table**, `project_info_activity_log`, a copy of
   `ingestion_activity_log` with `project_uuid` instead of `document_uuid` and an FK to
   `project_info_jobs`. Not a widened shared table: both FKs stay NOT NULL and the
   ingestion archive and prune paths stay untouched. Record the pair in
   `claude-stuff/ABSTRACTION_CANDIDATES.md` as a Longshot (two activity logs).
4. **"Active" means queued, running, or finished in the last 15 minutes**
   (`CONSOLE_RECENT_MINUTES = 15`, server-side). A job you just watched finish does not
   vanish from the default view. The filter options become: "Active" (default), "All",
   and the four single statuses.
5. **Auto-open after upload, filtered to that project.** Both upload paths open the main
   window with `{kind: 'ingest_console', data: {projectUuid}}`. The console shows a
   removable "Project: <name>" chip; clearing it shows all projects. Opened from the
   sidebar there is no project filter.
6. **Each row shows its latest activity line inline** (phase + message + relative time),
   so most of the time nobody needs to open the terminal.

## Changes

### 1. Project-info activity (backend)

- Table `server/shared/db/tables/project_info_activity_log.py` (register in
  `tables/__init__.py`), migration `sql/23_project_info_activity_log.sql` following the
  header style of `sql/20_project_info_jobs.sql`:

  | column | type | notes |
  |---|---|---|
  | `id` | bigint identity PK | cursor for tailing |
  | `job_uuid` | uuid FK project_info_jobs ON DELETE CASCADE | |
  | `project_uuid` | uuid FK projects ON DELETE CASCADE | |
  | `worker_id` | text NOT NULL | |
  | `phase` | text | `ProjectInfoPhase` value |
  | `message` | text NOT NULL | |
  | `ts` | timestamptz NOT NULL default now() | |

  Index `(job_uuid, id)`. No archive table: project-info jobs are few; prune rows older
  than `settings.activity_retention_hours` in the worker's existing housekeeping step.
- Model `NewProjectInfoActivity` / `ProjectInfoActivity`, repository
  `server/shared/repositories/project_info_activity.py` with `add_many`, `tail(job_uuid,
  after_id, limit)`, `delete_older_than(cutoff)`; UoW attribute
  `project_info_activity`.
- `ProjectInfoPhase(StrEnum)` in `server/shared/services/project_info/`: `claim`,
  `retrieve`, `synthesize`, `write`.
- Writer: generalise nothing. Add `ProjectInfoActivityWriter` next to `ActivityWriter`
  (same buffered flush, flush calls `uow.project_info_jobs.touch_lease`), which replaces
  the per-query `heartbeat()` callback in `project_info_loop.py`. `ProjectInfoService.run`
  takes an `activity: ActivityEmit` instead of `heartbeat`.

### 2. Copious status updates (backend)

Every line goes through `_activity(...)` (document jobs) or the new project-info emit;
they are cheap because they are buffered. Do not add `ingest_job_events` milestones;
those drive the project status bar and stay coarse.

Document ingestion (`ingestion_service.py`, `langchain_pipeline.py`, `worker/main.py`):
- start: file name, size in KB, detected kind (PDF / GAEB), attempt number (already
  partly emitted in the worker).
- download from storage: started / done with byte count and duration.
- thumbnails: page count up front ("rendering 42 pages"), then every
  `activity_thumbnail_every` pages (exists), then "stored 42 thumbnails".
- langchain: one line per stage inside the pipeline (load, split -> n chunks, embed
  progress every `activity_embed_every`, index -> n chunks).
- extract: "extracted n source lines from m pages".
- chunk: "n chunks drafted", embed progress (exists), "archived previous chunks",
  "indexed n chunks into <index>".
- GAEB: "parsed n items, m texts", "removed k stale positions", per item (exists),
  texts (exists).
- end: "done in 12.3 s" with the totals from `IngestionResult`; on failure the exception
  type and message (truncated to `FAILURE_MESSAGE_LIMIT`) before re-raising.

Each stage line carries its duration where a stage ends ("thumbnails done in 4.1 s"). Use a
small `time.monotonic()` pair inline; no timing helper.

Project-info job (`project_info_loop.py`, `project_info/service.py`):
- claim: attempt, language, overwrite flag, how many query versions were found.
- per query key: "retrieving <key> (v<version>)", "n chunks after rerank", "LLM:
  gefunden=<bool> konfidenz=<x>" plus the first 120 chars of `wert`, and "skip: column
  already set" / "skip: no query version" where those apply.
- write: "writing n columns: a, b, c" or "nothing to write".
- end: "done in x s, n of m found" or the failure.
- mock mode emits the same lines with "(mock)".

### 3. Console list with both kinds and the latest line (backend)

- `ConsoleJobKind` in `server/shared/models/enums.py`.
- Replace `IngestJobConsoleRow` / `IngestJobConsoleRead` with `ConsoleJobRow` /
  `ConsoleJobRead`: `kind`, `job_uuid`, `project_uuid`, `project_name`,
  `document_uuid | None`, `file_name | None`, `status`, `attempts`, `locked_by`,
  `locked_at`, `created_at`, `updated_at`, `latest_phase | None`,
  `latest_message | None`, `latest_ts | None`. Delete the old names (no shim); update
  `BODY_MODELS` and regenerate types.
- `IngestJobRepository.list_for_console` gains the latest activity line via a
  `LATERAL (SELECT ... ORDER BY id DESC LIMIT 1)` on `ingestion_activity_log` (the
  `(job_uuid, id)` index serves it), and a `recent_minutes` argument implementing
  decision 4. `ProjectInfoJobRepository.list_for_console` mirrors it over
  `project_info_jobs` + `project_info_activity_log`.
- `IngestAdminService.list_jobs(statuses, project_uuid, active)` merges both lists,
  newest `created_at` first. `active=True` replaces the client-side status list for the
  default filter.
- `GET /ingest-jobs` gains `active: bool = false`; response `list[ConsoleJobRead]`.
- `POST /ingest-jobs/{job}/requeue` stays ingest-only. Add
  `POST /ingest-jobs/project-info/{job}/requeue` via `ProjectInfoJobRepository.requeue`
  (reset to queued, clear lock and error, same as the ingest one).
- `GET /ingest-jobs/project-info/{job}/activity/stream`: the existing
  `stream_job_activity` loop over the new repository. Duplicate the function
  (`stream_project_info_activity`) rather than parameterising it; it is the second
  instance.

### 4. List stream (backend)

- `stream_console_jobs(engine, *, statuses, project_uuid, active, poll_interval)` in
  `ingest_admin.py`: each tick runs `list_jobs`, computes a fingerprint of
  `(kind, job_uuid, status, attempts, locked_by, latest_ts)` per row, and yields
  `{EVENT: "console_jobs", DATA: [rows]}` only when the fingerprint changed (the first
  tick always emits). Heartbeat as in `stream_project_status`. It never ends on its own;
  client disconnect ends it.
- `GET /ingest-jobs/stream` with the same query params as the list; SSE envelope model
  `ConsoleJobsSnapshot(event: Literal["console_jobs"], jobs: list[ConsoleJobRead])` in
  `ingest_schema.py`, added to `BODY_MODELS`.
- Unit test the fingerprint/diff as a pure function, like `diff_status`.

### 5. UI

- `ui/src/api/ingestJobs.ts`:
  - `useConsoleJobs(filters)`: `useQuery` with the list endpoint as `queryFn` and no
    `refetchInterval`, plus a stream effect that opens `/ingest-jobs/stream` for the same
    filters and calls `qc.setQueryData(ingestJobKeys.list(filters), snapshot.jobs)`.
    Reconnect after `RECONNECT_DELAY_MS` on error, abort on unmount or filter change
    (mirror `useIngestJobActivity`). Put the stream effect in the hook, not the view.
  - When a snapshot shows a project-info job turning `done`, invalidate
    `projectKeys.detail(project_uuid)` and `projectKeys.list()` so the project header
    refreshes.
  - `useRequeueProjectInfoJob`, and the activity hook takes `(kind, jobUuid)` to pick the
    stream path.
  - Remove `ACTIVE_POLL_MS`, `IDLE_POLL_MS`, `hasActiveJobs`.
- `ui/src/lib/sse-events.ts`: a `parseConsoleJobsPayload`.
- `IngestConsoleView.tsx`:
  - Remove the Refresh button and `manualRefreshing`.
  - Filter default `active`; options per decision 4.
  - Accept `data?: unknown` like `ProjectsView`; narrow `{projectUuid: string}` and show
    the removable project chip (decision 5).
  - Columns: Project, File (or "Projektinfo" with a distinct badge for
    `kind === "project_info"`), Status, Current step (latest phase in amber + message,
    truncated, full text in `title`, relative time), Attempts, Worker, Actions.
  - A small "live" dot next to the heading while the stream is connected, grey while
    reconnecting.
  - The file is ~200 lines today; if it crosses ~300, move the row into
    `ConsoleJobRow.tsx`.
- `MainWindow.tsx`: pass `view.data` to `IngestConsoleView`.
- `UploadDocumentDialog.tsx`: on success, close and
  `openMainWindow({kind: 'ingest_console', data: {projectUuid}})`.
- `ProjectsView.tsx` ZIP path: on `onCreatedFromZip`, open the console for the new
  project. The `skipped` note is lost that way, so show it in the console instead: pass
  `{projectUuid, skipped}` and render `SkippedZipEntriesNote` above the table when
  present (dismissible, as on the project page). Drop the `skipped` prop from the project
  detail path if nothing else uses it.
- `IngestActivityTerminal.tsx`: takes `kind` and uses the matching stream; title
  "Projektinfo activity" for the project-info kind.

### 6. Docs

- `AI_ARCHITECTURE.md`: the project-info pipeline section gets the activity log and its
  phases.
- `APPLICATION_ARCHITECTURE.md`: ERD + table list gain `project_info_activity_log`; the
  console section describes the list stream.
- `DEVOPS.md`: migration `sql/23`, applied after `sql/22`.
- `GLOSSARY.md`: "Ingest console" entry if missing.

## Tests

- Unit: console fingerprint diff (unchanged list -> no event, status change -> event,
  new row -> event); `ProjectInfoService.run` in mock mode emits the expected phase
  sequence through a fake emit; `ConsoleJobRead` validation for both kinds.
- Integration (`roadbuilders_t06_test`):
  - `list_for_console` returns the latest activity line per job and honours
    `recent_minutes` (a done job updated 5 min ago is in, 30 min ago is out).
  - `GET /ingest-jobs?active=true&project_uuid=...` returns both kinds for a project with
    one ingest job and one project-info job.
  - `GET /ingest-jobs/stream` emits a first snapshot, then a second one after a job's
    status is changed in the DB; read two events with a timeout and close.
  - Project-info requeue and activity stream (stream ends once the job is done and
    drained).
  - The worker project-info integration test (mock mode) leaves activity rows with all
    four phases.
- UI: `tsc` + eslint on touched files. Browser-verify on main after the merge: upload a
  PDF from a project page and a ZIP from the projects list; both land in the console,
  rows appear within ~2 s without interaction, the "Current step" column moves, the
  project-info row appears and goes queued -> running -> done, and the project header
  updates after it.

## Out of scope

- LISTEN/NOTIFY.
- Changing the project page's own ingest status bar (`useProjectIngestStatus`) or the
  `ingest_job_events` milestones.
- Cancelling a running job.

## Report

Files changed, tests run with results, migration verification output, anything left
open, proposed commit message.
