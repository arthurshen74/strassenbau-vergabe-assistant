# ZIP-first project creation: task plan

Goal: a user uploads one tender ZIP, a project is created, every PDF / X83 / D83 inside
(recursively) is ingested, each GAEB file becomes its own LV document, and once all
document ingestion for that project has finished a worker runs a set of versioned,
user-editable RAG queries that fill the project header fields.

The existing flow (create a project in a form, then upload documents) stays as is.

## Decisions already made (do not re-litigate)

1. **Per-GAEB LV datasets = per-document.** `lv_items`, `lv_texts` and their ES chunks are
   already keyed by `document_uuid`. "One LV dataset per GAEB file" means: drop the one-LV-
   document-per-project rule and stop replacing the existing LV document on upload.
   Nothing new is needed in the data model for this.
2. **Completion is a queue claim rule, not a flag on the ingestion service.** The ZIP flow
   enqueues one `project_info_jobs` row next to the document ingest jobs. The worker claims
   it only when the project has no queued or running `ingest_jobs` left. Only the ZIP flow
   (and an explicit "re-run" endpoint) ever enqueues one, so the old flow never triggers it.
   `IngestionService` is not touched.
3. **Queries are versioned rows in a new `rag_query_versions` table**, append-only like
   `prompt_versions`, keyed by `(query_key, language, version)`. `query_key` is a code enum
   (`ProjectInfoQuery`) because each key maps to a fixed `projects` column; new versions are
   data, new keys are code.
4. **Each query has two texts.** `query_text` is the retrieval question (what goes into the
   embedding and BM25). `answer_instruction` is the output rule for the synthesis LLM. They
   are never concatenated into one string for retrieval.
5. **Synthesis mirrors the project-context resolver.** One seeded system prompt
   (`project_info_resolve`), structured JSON output `{reasoning, gefunden, wert, konfidenz,
   beleg}`, one query per LLM call, PLUS retrieval with multi-query + BM25 + rerank. A miss
   (`gefunden=false`) leaves the column untouched. Free text never goes straight into a column.
6. **Language** comes from `settings.project_info_language` (env `PROJECT_INFO_LANGUAGE`,
   default `de`) at enqueue time and is stored on the job. Seed data is German because the
   tender documents are German and BM25 only matches in the document language. An `en`
   set can be added through the editor UI.
7. The placeholder project name for a ZIP-created project is the ZIP filename stem. The
   project-info job overwrites it.

## Tasks and dependencies

| Task | File | Depends on | Can run in parallel with |
|---|---|---|---|
| 01 Multi-LV backend | `01-multi-lv-backend.md` | - | 04 |
| 02 Multi-LV UI | `02-multi-lv-ui.md` | 01 | 03, 04, 05 |
| 03 Recursive ZIP + ZIP-first create | `03-zip-first-create.md` | 01 | 02, 04 |
| 04 RAG query versions (table, seed, API, editor UI) | `04-rag-query-versions.md` | - | 01, 02, 03 |
| 05 Project-info job, worker loop, resolver | `05-project-info-job.md` | 03, 04 | 02 |

## Execution waves (parallelism)

Run each wave as concurrent agents, one agent per task. Start the next wave only when every
task it depends on has reported done (tests green, types regenerated) **and has been merged
into main**. Each task file has a preflight check for this; a worktree created before the
merge does not contain the dependency and the agent will end up re-doing it.

```
wave 1:   [01 multi-LV backend]      [04 RAG query versions]
               |          \                 |
wave 2:   [02 multi-LV UI]  [03 ZIP-first create]
                                  |         |
wave 3:                        [05 project-info job]
```

- **Wave 1: 01 and 04 in parallel.** They touch disjoint files. 01 edits documents /
  retrieval / project_service / chat agent; 04 adds a new table, repository, route, seed
  package and UI view, and registers them in `tables/__init__.py`, `unit_of_work.py`,
  `export_schema.py` and `config.py`, none of which 01 touches.
- **Wave 2: 02 and 03 in parallel**, both after 01. 02 is UI only (`ui/src/views/main/`,
  `ui/src/api/projects.ts`). 03 is backend + one dialog. Shared file: `ui/src/api/projects.ts`
  (02 adds per-document hooks, 03 adds `useCreateProjectFromZip`); both append new exports,
  so a merge is mechanical. 04 may still be running during wave 2; neither 02 nor 03 needs
  it.
- **Wave 3: 05 alone**, after 03 and 04. Its table, repository, resolver service, prompt and
  worker loop can be started as soon as 04 reports done (they only need
  `RagQueryVersionRepository`, `ProjectInfoQuery` and the setting); the enqueue call into
  `ProjectService._after_zip_ingest` and the end-to-end check wait for 03. 02 may still be
  running; 05 adds a status line to `ProjectDetails.tsx`, which 02 also edits, so whichever
  finishes second rebases its edit onto the other's version of that file.

Shared files that more than one task edits (coordinate or rebase, never overwrite):
`ui/src/api/projects.ts` (02, 03, 05), `ui/src/views/main/ProjectDetails.tsx` (02, 05),
`server/api/routes/projects.py` (01, 03, 05), `server/shared/services/project_service.py`
(01, 03, 05), `server/shared/models/project_schema.py` (03, 05), `server/shared/config.py`
(04, 05), `.env.example` (04, 05), `server/shared/db/tables/__init__.py` and
`server/shared/db/unit_of_work.py` (04, 05), `server/scripts/export_schema.py` (04, 05),
`server/shared/models/enums.py` (04 adds `ProjectInfoQuery`, 05 adds a `PromptType`).

## Worktree setup (one worktree per task)

Each task runs in its own git worktree and branch; Arthur merges the branches into main at
the end of each wave, runs the full suite on main, applies the wave's migrations to the dev
database, and starts the next wave from main.

```bash
# from the main checkout, after the current work is committed
git worktree add ../swa-task01 -b task/01-multi-lv
cd ../swa-task01
uv sync                      # per-worktree .venv
(cd ui && npm ci)            # per-worktree node_modules
```

The `tasks/` folder is tracked, so every worktree carries this plan.

Rules for an agent inside a worktree:

- **One shared compose stack.** Postgres, Elasticsearch, MinIO and Phoenix run once, from
  the main checkout. Never run `docker compose up`, `restart` or `down` from a worktree: a
  second stack collides on the ports and would mount an empty `./data`.
- **Own test database.** The integration fixture drops and recreates every table in
  `{POSTGRES_DB}_test` at session start, so concurrent agents must not share it. Create one
  per task on the shared Postgres and point pytest at it:

  ```bash
  docker exec strassenbau-vergabe-assistant-postgres \
    psql -U roadbuilders -d postgres -c "CREATE DATABASE roadbuilders_t01_test"
  POSTGRES_DB=roadbuilders_t01 PYTHONPATH=server uv run pytest tests/integration/...
  ```

  Only the test URL is derived from that variable in tests; the dev database `roadbuilders`
  is untouched. Run `tests/integration/search` only in the final check, since those tests
  write to the shared ES index by name.
- **The api, worker and ui containers serve main's code** (they bind-mount the main
  checkout's `server/` and `ui/`). Code in a worktree is verified with tests, tsc and eslint.
  Browser verification against `localhost:5173` happens on main after the merge.
- **Migrations** are verified on a scratch database inside the task and applied to the dev
  database by Arthur after the wave is merged.
- Commit on the task branch only if asked; otherwise leave the tree and report. Never touch
  main from a worktree.

## Reserved migration numbers

Migrations are hand-written SQL in `sql/` (there is no migration tool; `create_all` only
adds missing tables). Numbers are reserved here so parallel tasks do not collide:

| File | Task |
|---|---|
| `sql/18_multi_lv_documents.sql` | 01 |
| `sql/19_rag_query_versions.sql` | 04 |
| `sql/20_project_info_jobs.sql` | 05 |
| `sql/21_project_info_resolve_prompt_type.sql` | 05 |

Follow the header style of `sql/16_lv_texts.sql` and `sql/17_projects_massnahme.sql`:
a comment block (what, why, mirrors which table file, idempotent, run-after), then
idempotent DDL. Verify each script on a scratch database before finishing (pattern:
create a scratch DB, create the referenced parent tables as stubs, run the script twice,
`\d` the result and compare with what `create_all` builds in `roadbuilders_test`).

## Conventions that apply to every task

- Read `CLAUDE.md` first. Core + Pydantic only, repositories take an `AsyncConnection`,
  logic lives in `server/shared/services`, routes are thin.
- Contract literals (column names, discriminator values, ES field names) are module
  constants or `StrEnum` members, never inline strings. CHECK constraints are built from the
  enum (see `server/shared/db/tables/lv_texts.py`).
- `uvx ruff format <only the files you edited>` and
  `uvx ruff check --isolated --line-length 88 --select E,W,F <those files>`. Never run
  ruff on the whole tree: `tests/` and markdown code blocks are not ruff-clean and a tree-
  wide format rewrites 80+ unrelated files.
- Backend DTO change => `cd ui && npm run gen:types`. Never hand-edit
  `ui/src/types/generated.ts`.
- Tests: `PYTHONPATH=server uv run pytest tests/unit -q` and the relevant
  `tests/integration/...` files (the test DB `roadbuilders_test` is rebuilt with
  `drop_all`/`create_all` per session, so new tables need no migration there). UI:
  `cd ui && npx tsc --noEmit -p tsconfig.app.json && npx eslint <files>`.
- Update the root docs a change touches: `APPLICATION_ARCHITECTURE.md` (ERD, layers),
  `AI_ARCHITECTURE.md` (pipelines), `GLOSSARY.md`, `DEVOPS.md` (new env vars, seeding),
  `README.md` (first-project walkthrough).
- No `git commit` / `git push` / `git add`. Leave changes in the working tree and report.
- Each task ends with a short report: files changed, tests run with results, anything left
  open, and a proposed commit message.

## Current state to be aware of

- Commit `1cc45d1` carries the groundwork this plan builds on: `lv_texts` (table, repo,
  parser, chunks, UI tab) and the project header fields (`massnahmenummer`, `bauleistung`,
  nullable `vergabe_id` / `vergabestelle` / `project_description`, `PATCH /projects/{uuid}`,
  `EditProjectDialog`). `sql/16_lv_texts.sql` and `sql/17_projects_massnahme.sql` are
  applied to the dev DB.
- The live ES index has no `LV_TEXT` chunks yet; that is a data problem the owner will
  solve by re-ingesting, not a code problem.
