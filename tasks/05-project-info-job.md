# Task 05: Project-info job, worker loop and resolver

Depends on: 04 (queries, `ProjectInfoQuery`, setting), 03 (the `_after_zip_ingest` seam).
The table, repository, service and worker loop can be built before 03 lands; only the
enqueue call and the end-to-end check need it.

## Use a worktree

Preflight, on `main` before creating the worktree. If this fails, the dependency is
not merged yet: stop and report instead of re-doing the other task's work.

```bash
test -f sql/18_multi_lv_documents.sql && test -f sql/19_rag_query_versions.sql \
  && grep -q _after_zip_ingest server/shared/services/project_service.py   # 01, 04, 03 merged
```

Work in a dedicated git worktree and branch, never in the main checkout:

```bash
git worktree add ../swa-task05 -b task/05-project-info-job
```

Follow the "Worktree setup" section of `tasks/README.md` for the rest: per-worktree
`uv sync` and `npm ci`, your own test database (`POSTGRES_DB=roadbuilders_t05`
for pytest), one shared compose stack that you never start or restart, migrations
verified on a scratch database only, and no commits unless asked.

## Goal

After the ZIP flow has enqueued a project's documents, exactly one project-level job waits
until none of that project's ingest jobs is queued or running, then runs the six RAG queries
(latest version for the job's language) through PLUS retrieval and a structured synthesis
LLM call, and writes the found values into the `projects` columns. Status and result are
visible on the project page, and a "re-run" endpoint exists for existing projects.

## Precedent to mirror

`server/shared/services/project_context/service.py::_resolve_one` and
`server/shared/services/project_context/llm.py::resolve_globale`: per variable, retrieve
with `RESOLVE_RETRIEVAL_CONFIG` (PLUS, multi-query, BM25, cross-encoder), pass the chunk
texts as snippets to one structured LLM call (`GlobaleAufloesung`: reasoning, gefunden,
wert, konfidenz, beleg), skip when not found. Seeded prompt
`server/scripts/seed/prompts/project_context_resolve.prompt`. The queue mechanics to mirror
are `IngestJobRepository.claim_next` / `EvalRunRepository.claim_next` (FOR UPDATE SKIP
LOCKED, lease, attempts) and `server/worker/eval_loop.py` (a second loop sharing the
worker process).

## Changes

### Table and model
`project_info_jobs` (`server/shared/db/tables/project_info_jobs.py`, register in
`tables/__init__.py`, UoW attribute `project_info_jobs`), migration
`sql/20_project_info_jobs.sql`:

| column | type | notes |
|---|---|---|
| `job_uuid` | uuid PK | |
| `project_uuid` | uuid FK projects ON DELETE CASCADE, index | |
| `language` | text NOT NULL | copied from `settings.project_info_language` at enqueue |
| `overwrite` | boolean NOT NULL default false | true: write every found value; false: only fill NULL columns |
| `status` | text NOT NULL default `queued` | reuse `IngestStatus` + CHECK |
| `locked_at`, `locked_by`, `attempts` | as `ingest_jobs` | |
| `error` | text | last failure message |
| `result` | jsonb | per query_key: `{wert, konfidenz, beleg, gefunden, query_version}` |
| `created_at`, `updated_at` | timestamptz | |

Index `(status, locked_at)` like `ingest_jobs`. Models in
`server/shared/models/project_info_job.py` (`ProjectInfoJob`, `NewProjectInfoJob`,
`ProjectInfoResult` for the jsonb shape). API DTO `ProjectInfoJobRead` in
`project_schema.py` or a new `project_info_schema.py`; add to `BODY_MODELS`.

### Repository
`server/shared/repositories/project_info_jobs.py`:
- `add(new) -> ProjectInfoJob`.
- `claim_next(*, worker_id, lease_seconds, max_attempts) -> ProjectInfoJob | None`: same
  shape as the ingest claim with one extra predicate on the candidate row:
  `NOT EXISTS (SELECT 1 FROM ingest_jobs j JOIN documents d ON d.document_uuid =
  j.document_uuid WHERE d.project_uuid = project_info_jobs.project_uuid AND j.status IN
  ('queued','running'))`. FAILED document jobs do not block (otherwise one poison document
  would hold the project-info job forever); note that in the docstring.
- `set_status(job_uuid, status, *, expected_worker, error=None, result=None)` fenced on the
  lease like `IngestJobRepository.set_status`.
- `latest_for_project(project_uuid) -> ProjectInfoJob | None`.
- `has_open_job(project_uuid) -> bool` (queued or running) so a re-run request while one is
  pending returns the existing job instead of enqueuing a second.

### Resolver service
`server/shared/services/project_info/` package:
- `queries.py`: `PROJECT_INFO_TARGET_COLUMNS: dict[ProjectInfoQuery, str]` imported from
  task 04's `rag_query.py` (do not duplicate the mapping; if task 04 placed it there, import
  it). Retrieval config `PROJECT_INFO_RETRIEVAL_CONFIG` = PLUS, multi_query, BM25, cross-
  encoder (a copy of the project-context one with its own name, per the local-mirroring
  convention in that module).
- `llm.py`: `ProjektInfoAufloesung` (same fields as `GlobaleAufloesung`) and
  `resolve_project_info(llm, query: RagQueryVersion, snippets, *, prompt, project_uuid)`.
  The user message carries `{"name", "description", "answer_instruction", "language"}` and
  the snippets, same shape as `resolve_globale`. The system prompt is the new seeded
  `project_info_resolve.prompt`.
- `service.py`: `ProjectInfoService.run(job: ProjectInfoJob, *, retrieval, llm, prompt,
  uow_factory) -> ProjectInfoResult`. For each `ProjectInfoQuery`: `get_latest(key,
  job.language)`; if None, record `{"gefunden": false, "error": "no query version"}` and
  continue; else `retrieval.retrieve_context(query.query_text, project_uuid, config)`,
  synthesize, and when `gefunden and wert`: update the target column (`ProjectRepository.
  update`) subject to `overwrite` (read the project once at the start; with
  `overwrite=false` skip columns that are not NULL; `project_name` counts as NULL when it
  still equals the ZIP placeholder, which the job cannot know, so the ZIP flow simply
  enqueues with `overwrite=true`). Store the whole per-key result on the job row. In
  `settings.calculator_mock`, skip retrieval and LLM and return fixed values like
  `_MOCK_WERTE` in the project-context service, so the worker integration test runs offline.
- `location` is written as text only; geocoding stays with the project-context resolver.

### Prompt
- `PromptType.PROJECT_INFO_RESOLVE = "project_info_resolve"` in `enums.py`;
  `server/scripts/seed/prompts/project_info_resolve.prompt` with the same frontmatter style
  as `project_context_resolve.prompt`; rules: use only the snippets, follow
  `answer_instruction` for the value format, `gefunden=false` when the snippets do not
  support an answer, `beleg` = literal quote, 2-5 reasoning steps first, answer in the
  given `language`.
- `sql/21_project_info_resolve_prompt_type.sql`: widen the two `prompt_type` CHECK
  constraints exactly as `sql/15_ner_fehleranalyse_prompt_type.sql` does (copy its current
  list and add the new value). Then run the prompt seeder once against the dev DB.

### Worker
- `server/worker/project_info_loop.py` mirroring `eval_loop.py`: `process_one_project_info`
  (claim, build `RetrievalService` from the engine/llm/embeddings/search/reranker already
  constructed in `run_worker`, load the latest `PROJECT_INFO_RESOLVE` prompt, run the
  service, set DONE with result or FAILED with error, log one line per outcome) and
  `project_info_loop` polling with `settings.worker_poll_interval_seconds`.
- `run_worker`: add the loop to the `asyncio.gather`. Update the module docstring, which
  describes the two loops.

### Enqueue
- Replace the no-op `ProjectService._after_zip_ingest(project_uuid)` from task 03 with
  `await self.project_info_jobs.add(NewProjectInfoJob(project_uuid=..., language=settings.
  project_info_language, overwrite=True))`. The service gains an optional
  `project_info_jobs` repository parameter like the others; the from-zip route's DI passes
  `uow.project_info_jobs`.
- `POST /projects/{p}/project-info/run` body `{"overwrite": bool}` -> 202
  `ProjectInfoJobRead` (returns the open job if one exists). `GET /projects/{p}/project-info`
  -> latest job or 404. Logic in `ProjectService` (or a small `ProjectInfoJobService` if
  `project_service.py` would cross ~400 lines; it is close already, so prefer the new file).

### UI
- `ui/src/api/projects.ts`: `useProjectInfo(projectUuid)` with `refetchInterval` of 3 s
  while status is queued/running, and `useRunProjectInfo(projectUuid)`; on a status change
  to done invalidate `projectKeys.detail` and `projectKeys.list`.
- `ProjectDetails.tsx` header: a small status line "Projektinfo: wartet auf Ingestion /
  läuft / fertig (n von 6 gefunden) / fehlgeschlagen" when a job exists, and a "Projektinfo
  neu ermitteln" button (outline) that calls the run endpoint with `overwrite=true` after
  a confirm dialog (reuse the dialog pattern of `DeleteProjectDialog`). For a done job show
  per-field found/not-found with the `beleg` quote in a tooltip or an expandable row;
  keep it compact.

### Tests
- Repository (`tests/integration/repositories/test_project_info_jobs.py`): not claimable
  while the project has a queued ingest job; claimable once that job is DONE; claimable when
  it is FAILED; another project's open jobs do not block; lease/attempts behave like the
  ingest claim; `has_open_job`.
- Service (`tests/unit/services/test_project_info_service.py`) with fakes for retrieval,
  LLM and repositories: found values written, `gefunden=false` leaves the column, missing
  query version recorded, `overwrite=false` skips non-NULL columns, result json shape.
- Worker (`tests/integration/worker/test_worker.py` pattern) in mock mode: a project with
  one document job DONE and a queued project-info job ends DONE with the mock values on the
  project row.
- API: run endpoint returns the existing open job on a second call; GET 404 when none.
- From-zip end to end (extends the task 03 API test): after `POST /projects/from-zip` one
  queued `project_info_jobs` row exists for the new project with `language` from settings.

### Docs
- `AI_ARCHITECTURE.md`: new section "Project info extraction" with a short state diagram:
  documents queued -> all done -> project-info job claimed -> per-query retrieve+synthesize
  -> columns written. Mention the no-free-text rule and the two-text query design.
- `APPLICATION_ARCHITECTURE.md`: ERD entity `project_info_jobs`; the worker now runs three
  loops.
- `DEVOPS.md`: new prompt type (seeding), migration 20/21, env var.
- `GLOSSARY.md`: Projektinfo.

## Done when
- Uploading a ZIP on the dev stack ends, without manual steps, with the header fields filled
  for the found values and the status line showing done; a re-run on an existing project
  works; a project whose ingestion partially failed still gets its project info.
- All tests above pass; types regenerated; docs updated.
