# CLAUDE.local.md

Guidance for working in this repository. Auto-loaded by Claude Code at the start of every session.

## Repository Layout

### server/

A backend Python 3.12, FastAPI/Pydantic/SQLAlchemy server. Dependencies are managed with `uv` from the root `pyproject.toml`; `uv sync` builds the project `.venv`.

```bash
uv sync          # create/update .venv from pyproject.toml + uv.lock (incl. dev tools)
uv run pytest    # run any command inside the venv
```

- `server/` - the backend server code, Python 3.12. Deps live in the root `pyproject.toml`; run commands from the repo root with `uv run`.
- `server/api` - this is the endpoint surface for the API that is exposed via HTTP. It is a thin wrapper. ALL LOGIC for api routes needs to go in `server/shared/services`.
- `server/api/routes` - each API resource gets it's own file.
- `server/shared/` - common logic for both API and WORKER, but NOT AUTH (fastapi-users), that get's it's own directory `auth/`.
  — `server/shared/db/` - SQLAlchemy Core: tables, shared MetaData, custom types, Unit of Work
- `server/shared/models/` - Pydantic models, both domain and API Schema.
- `server/shared/repositories/` - Core-backed, take an `AsyncConnection`
- `server/shared/services/` - Business logic goes here.
- `server/shared/clients/` - Shared infrastructure clients such as `llm` (OpenAI/OpenRouter Transport), `search` (Elasticsearch), `storage` (MiniIO/S3 - boto)
- `server/scripts/` - server scripts like seeding data.
- `server/worker/` - harness for long-running processes like ingestion or retrieval. The logic should be in `shared/` but the actual worker process stuff (messaging, status, threads) should be in `worker/`

### /test

Integration and unit tests go here.

- `tests/integration` - Here we can tests APIs and repositories and clients.
- `tests/unit` - Here we place the unit tests for models, repositories, services, clients

### /ui/src

A Vite + React 19 + TypeScript app. Tailwind for styling. Routing is in `App.tsx` (`react-router-dom` `BrowserRouter`/`Routes`); the `QueryClientProvider` is set up in `main.tsx`.

- `api/` - server-state layer. One file per resource (`projects.ts`, `documents.ts`, `conversations.ts`, `ingestJobs.ts`, `logs.ts`, `prompts.ts`, `calculations.ts`), each exporting React Query `useQuery`/`useMutation` hooks plus a typed query-key factory (e.g. `projectKeys`). `client.ts` is the thin fetch wrapper; `sse.ts` handles Server-Sent Events.
- `store/` - Zustand stores for client/UI state only (`mainWindow`, `drafts`, `retrievalConfig`, `ui`). Server state belongs in `api/`, not here.
- `views/` - route-level and feature views (`ConversationRouter.tsx`, `Home.tsx`, and feature folders `calculator/`, `main/`, `workspace/`). Feature-specific React Query hooks are co-located here (e.g. `views/calculator/useCalculatorConversation.ts`, `views/workspace/hooks/`).
- `components/` - shared presentational components, grouped by area (`chat/`, `feedback/`, `layout/`, `mainwindow/`, `ui/`).
- `lib/` - framework-agnostic utilities (formatting, logging, SSE event parsing, slash commands).
- `types/generated.ts` - generated from the backend schema (never hand-edit; `npm run gen:types`).

### Miscellaneous

- `eval/` - anything that has to do with generating evaluation data.

## Coding Conventions

### Comments

- Default to writing simple comments, what it does, NOT WHY.
- Only specify the _why_ when it is not obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug, behaviour that would surprise a reader.
- Write simple and short _what_ comments where appropriate for a senior engineer.
- Never write justifications, change history, or task references ("added for the X flow", "used by Y", "fixes #123"). Those belong in PR descriptions and rot.
- You may write multi-line, multi-paragraph doc strings only at the top of a file and that is to provide a human readable description of the contents of the file (modules, functions, etc.)

### Constants and magic strings

- No magic strings. A string literal that names something in an external contract — a datastore field name, an index/column/key name, a discriminator value — must be a module-level `SCREAMING_SNAKE` constant, not an inline literal.
- The constant is the single source of truth: the _same_ constant is referenced on every side of the contract. A field name used when writing must be the same constant used when reading (e.g. ES `index_*` and `search` reference one `FIELD_PROJECT_UUID`, never two copies of `"project_uuid"`). This is what stops a rename from silently breaking one side.
- Controlled value sets (discriminators, status vocabularies) are `StrEnum`, not loose constants — see `ChunkType`, `IngestStatus`. Use the enum member everywhere; never re-type its value.
- Scope the constant to the module that owns the contract. Don't build a global "constants" dumping ground; a field name lives next to the client that owns the index/table.
- This is not a DRY judgement call — a contract literal used in two places is promoted on the _second_ use, not the fourth.

### DRY (and when not)

- Duplicate freely up to three similar instances. The shape of the abstraction is rarely clear before then.
- Keep a list of abstraction candidates inABSTRACTION_CANDIDATES.md. This list will be populated with 2 similar instances as "Longshots" and 3 similar instances as "Good Bet".
- Extract on the fourth instance, or when the duplication crosses a module boundary. If the abstraction is in the candidates list, remove it once the extraction is complete.
- Premature abstraction is worse than duplication. Three explicit, similar functions are easier to change than one parameterised helper guessed at the wrong dimensions.

### Abstractions, layers, helpers

- Don't add features, refactor, or introduce abstractions beyond what the task requires.
- A bug fix doesn't need surrounding cleanup. A one-shot operation doesn't need a helper.
- No half-finished implementations. No "we might want this later" hooks.

### Error handling

- Trust internal code and framework guarantees. Don't validate that a non-nullable field is non-null.
- Validate at system boundaries only: user input, external APIs, file parses, LLM responses (already enforced via Pydantic schemas).
- Don't add fallbacks for scenarios that can't happen. If they happen, you want a crash and a stack trace, not silent recovery.
- Logs at boundaries, not inside helpers. One log per failure, not three.

### Backwards compatibility

- Don't add backwards-compat shims, deprecated re-exports, or `# removed` placeholder comments.
- If something is unused, delete it. Git history is the audit trail.
- No feature flags for code paths that can simply be replaced.

### Python specifics

- Full type annotations on every public function. `from __future__ import annotations` in every module.
- Pydantic `BaseModel` for every DTO. `ConfigDict(extra="forbid")` by default.
- `async def` for any function that awaits I/O. No mixing sync DB calls into async handlers.
- Imports ordered: stdlib, third-party, first-party. One blank line between groups.
- Prefer `pathlib.Path` over `os.path`.
- No bare `except:`. Catch specific exceptions or let them propagate.

### TypeScript / React specifics

- No `any`. If a type is genuinely unknown, use `unknown` and narrow.
- Components are function components. No class components.
- One component per file, named export. Co-located styles only if Tailwind isn't enough (it usually is).
- Shared React Query hooks live in `ui/src/api/` (one file per resource); feature-specific hooks are co-located under the relevant `ui/src/views/{feature}/` folder.
- Imports ordered: react/third-party, `@/` first-party, relative. Auto-managed by Prettier/ESLint.
- Prefer composition over `useEffect`. If you reach for `useEffect`, ask whether React Query or a derived value would do the job.

### File and function size

- Function over ~50 lines: consider splitting. Not a hard rule — clarity wins.
- File over ~400 lines: probably two concerns. Split.
- Module (directory) over ~10 files: probably needs a sub-grouping.

## Where to look for what (Companion Documents)

- Look for model definitions in `server/shared/models`. A DATA_SCHEMA.md document will have human-readable descriptions of the models and entities with Mermaid Class and ERD diagrams.
- For detailed data layer architecture information, read DATA_ARCHITECTURE.md.
- Domain terms are listed in GLOSSARY.md.

## Things to Not Do

- Don't edit `ui/src/types/generated.ts`.
- Don't translate German domain terms. `Leistungsverzeichnis`, not `bill_of_services`.
- Don't import from `auth/` in `server/`. Auth is reachable via HTTP only.
- Don't put auth tables in the domain MetaData. `users`, `roles`, `oauth_*`, `sessions` belong to `auth/`'s database.
- Don't run a cross-database query or set up `postgres_fdw`. The domain DB and auth DB never JOIN.
- Don't use the SQLAlchemy ORM. Core + Pydantic only — no `DeclarativeBase`, no `Session`, no `Mapped[...]` annotations.
- Don't pass the engine to a repository. Repositories are constructed with an `AsyncConnection` so transactions compose across repositories that share the same connection.
- Don't add emojis to code, comments, commit messages, or documentation unless explicitly asked.
- Don't run `git commit` or `git push` — I do all commits myself. Leave changes in the working tree and report what changed; draft a commit message only when I ask for one. `git add` only on explicit request.
