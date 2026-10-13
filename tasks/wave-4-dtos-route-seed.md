# Wave 4 — DTOs, export_schema, UI regen, prompts route, seed

Read `tasks/README.md` first. **Depends on Wave 2B** (`PromptVersionRepository` + Unit of Work).
This wave makes the API surface real again and regenerates the TS types. The current
`server/scripts/export_schema.py` and `server/scripts/seed/prompts.py` still import the **old**
(deleted) `api.schemas.*` / `prompts` shapes — they are rewritten here.

## 4.1 — API DTOs (`server/shared/models/*_schema.py`)

Separate type family from domain models; `Create`/`Read`/`Update` suffix; `extra="forbid"`. Mirror the
domain models in `server/shared/models/` (already built). See `DATA_ARCHITECTURE.md` §4 for the exact
pattern.
- `project_schema.py` — `ProjectCreate`/`ProjectRead`/`ProjectUpdate`.
- `document_schema.py` — `DocumentRead`/`DocumentCreate` (uses `DocumentType`).
- `ingest_schema.py` — `IngestJobRead`, `IngestStatusRead`, `IngestJobEventRead`, and the SSE
  discriminated-union payloads `IngestStarted`/`IngestProgress`/`IngestCompleted`/`IngestError`
  (keep the `IngestEvent` union the export script emits).
- `prompt_version_schema.py` — `PromptVersionRead`/`PromptVersionCreate` exposing `prompt_type`,
  `version`, `model_name`, sampling fields, `initial_messages` (a `ChatMessage` DTO).
- Unit tests in `tests/unit/models/test_dtos.py`: DTO↔domain field parity for exposed fields;
  `extra="forbid"`.

## 4.2 — Rewrite `server/scripts/export_schema.py`

Keep the json2ts bundling, `_strip_titles`, and union-append machinery **as-is**. Only change the
imports + `BODY_MODELS`/`PINNED_MODELS`/`UNIONS` to the new DTO modules (drop the eval-era
`UploadResponseDTO`/`DocumentTypeDTO`/`ProjectDocumentDTO`). It remains the **only** writer of
`ui/src/types/generated.ts`. Rewrite `tests/unit/api/test_export_schema.py` (skip if json2ts absent):
`render()` contains every DTO interface + the `IngestEvent` union and is stable across calls.

## 4.3 — Regenerate `ui/src/types/generated.ts`

Run `npm run gen:types` (`docker compose exec -T api python -m scripts.export_schema`) or
`python -m scripts.export_schema` locally with `ui/node_modules/.bin/json2ts` present. **Never
hand-edit** the generated file. Verify `npm run check:types` is clean. The current file still has the
stale `ProjectDTO{project_id,...}` etc. — it will be fully replaced.

## 4.4 — Rewrite the prompts route

Fresh `server/api/routes/prompts.py` over a thin `PromptService` in `server/shared/services/`
(CLAUDE.local: route logic lives in services) backed by `PromptVersionRepository`. **PromptVersion-only
model** — no `Prompt` parent, no `slug`, no `api_type`. Endpoints: list versions by `prompt_type`, get
`(prompt_type, version)` and `latest`, create a new (immutable) version. Re-register the router in
`server/api/main.py` (the `include_router(prompts.router)` line was removed in Wave 0). Fresh
`tests/integration/api/test_prompts.py` via `httpx.AsyncClient` with the `get_uow`/`get_connection`
deps overridden to the test connection: create → `version=1`, again → `version=2`, get latest/pinned,
404 on missing.

## 4.5 — Rewrite the prompt seed

Fresh `server/scripts/seed/prompts.py`: seed one v1 `PromptVersion` per `PromptType` member
(`dispatcher`, `project_chat`, `classify_project_chat_user_message`, `multi_question_generator`,
`lv_extraction`) with a `model_name` (e.g. `anthropic/claude-sonnet-4.6`), sensible `temperature`, and
empty `initial_messages`. Idempotent upsert on `(prompt_type, version)`. Verify: run against the
compose DB shows 5 v1 rows; a re-run is a no-op.

## Done when

DTOs exist + tests pass; `export_schema` runs and `npm run check:types` is clean; `GET /prompts/...`
returns seeded versions; the API + seed integration tests are green.
