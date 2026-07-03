# Abstraction Candidates

Tracked duplication that is NOT yet worth extracting (see `CLAUDE.local.md` "DRY (and when not)").
Duplicate freely up to three similar instances. **Longshot** = 2 similar instances; **Good Bet** = 3.
Extract on the fourth instance, or when the duplication crosses a module boundary. Remove an entry once
its extraction is complete.

## Longshots (2 instances)

### ES archive-then-delete-by-query (reindex to `_archive` with `archived_at`, then `delete_by_query`)

- `server/shared/clients/search/client.py` — `SearchClient.archive_source` (re-ingestion, single source)
- `server/shared/clients/search/client.py` — `SearchClient.archive_and_delete_document` (document delete, compound footprint query)

Both `_ensure_archive_index`, `reindex` the matching query into the archive index with a painless
script stamping `archived_at`, then `delete_by_query` the same query from the live index, returning the
deleted count. Only the query differs (single `(source_doc_uuid, source_doc_type)` vs the document
footprint). **Do not extract yet** — same module, two callers. If a third archive-then-delete site
appears, extract a private `_archive_and_delete_by_query(query) -> int` helper.

### Shared OpenRouter HTTP transport (auth header + POST + `raise_for_status` + boundary log)

- `server/shared/clients/embeddings/client.py` — `EmbeddingsClient`
- `server/shared/clients/llm/client.py` — `LLMClient`

Both build `{"Authorization": f"Bearer {api_key}"}`, POST JSON to an OpenRouter URL, call
`raise_for_status()`, and log one boundary error. A third copy will arrive when the **rerank** client is
built (config exists: `settings.openrouter_api_url_rerank`, `settings.cross_encoder_model`).

**Do not extract yet.** The error handling already diverges (`LLMClient` raises
`RefusalError`/`OutputTruncatedError` and sends `response_format`; `EmbeddingsClient` validates vector
dimensions), and forcing the not-yet-written rerank client through a base would invent a contract before
its consumer exists. Revisit when rerank lands (the 3rd copy) — if the auth+POST shell is still uniform,
extract a thin transport then.

### Ingestion bootstrap + run-one-job lifecycle (build clients, construct IngestionService, set DONE/FAILED)

- `server/scripts/run_ingest_job.py` — `run_ingest_job` (manual single job by uuid; gets the job, marks RUNNING)
- `server/worker/main.py` — `process_one` (worker loop; claims the job, which marks RUNNING)

Both build the same client stack (`build_storage_client`, `SearchClient.from_settings`,
`EmbeddingsClient`, `LLMClient`, `LangchainIngestor`) + `ensure_index`, open a prompt connection to
construct `IngestionService`, run `ingest_document`, then `set_status` DONE / FAILED with the same
result-count log line. They differ in how the job is obtained (get-by-uuid vs `claim_next`) and in
failure behaviour (the script re-raises; the worker swallows to keep looping). **Do not extract yet** —
two callers. If a third runner appears, extract a shared `run_ingest(stack, job)` (and a stack builder)
into `shared/services/ingestion`.

### Duplicated write-tool test driver `_call` (ainvoke a tool_call dict, return the artifact)

- `tests/integration/services/test_katalog_schreib_werkzeuge.py` — `_call`
- `tests/integration/services/test_katalog_e2e.py` — `_call`
- `tests/integration/services/test_katalog_rezept_werkzeug.py` — `_call`

Identical four-liner: `tool.ainvoke({"type": "tool_call", ...})` and return `msg.artifact`. **Do not
extract yet** — three test files, trivially small. A fourth katalog-tool test file extracts a
`werkzeug_aufrufen` helper into a tests-side conftest or helper module. (Good Bet, listed under
Longshots layout-wise to keep entity order; 3 instances.)

### OpenRouter-backed ChatOpenAI construction (base-url suffix strip + secret key wrap)

- `server/shared/services/project_chat_agent.py` — `_openrouter_base_url()` + `ChatOpenAI(...)` (streaming chat agent, telemetry callbacks)
- `server/shared/services/calculator/llm_calls.py` — `_llm()` (structured-output sites, no streaming)
- `server/shared/services/katalog/chat_agent.py` — `_openrouter_base_url()` + `ChatOpenAI(...)` (katalog chat agent; the Phase-3 eval script reuses this via `KatalogChatAgent.ainvoke`, so it is NOT a fourth copy)

All strip `/chat/completions` off `settings.openrouter_api_url_chat` and build a `ChatOpenAI` with
`convert_to_secret_str(settings.openrouter_api_key or "")`. The construction diverges after that
(streaming + usage accounting + callbacks vs `with_structured_output`). **Good Bet (3 instances) —
extract on the fourth**: a `build_chat_model(model, **kwargs)` in `shared/clients/llm`.

### Duration-by-rate formulas (quantity / hourly performance)

- `server/shared/services/calculator/formulas.py` — `duration_by_performance` (m3 / m3-per-h)
- `server/shared/services/calculator/formulas.py` — `duration_by_area_performance` (m2 / m2-per-h)

Same division, different unit vocabulary. Kept separate deliberately: the formula id is the registry's
unit contract (a YAML row binding an m2 quantity to an m3 formula should fail loudly, not coerce).
**Do not extract yet** — if a third unit arrives (t/h for Mischgut), reconsider a unit-typed
`duration(quantity, rate)` instead of a third copy.

### Underline tab navigation (desktop `border-b-2` button bar)

- `ui/src/views/main/DocumentDetailDialog.tsx` — thumbnails / chunks / log tabs (icons + mobile `<Select>`)
- `ui/src/views/main/ProjectDetails.tsx` — LV Positions / Documents tabs

Both render the same desktop underline tab bar (`border-b` container, `-mb-px flex` nav, per-tab
`border-b-2` button with the indigo active state). DocumentDetailDialog additionally carries per-tab
icons and a mobile `<Select>` fallback. **Do not extract yet** — two callers and the shapes differ. If a
third tab bar appears, extract a `Tabs` component into `ui/src/components/ui/`.

> Note: the usage parser + sink (`server/shared/clients/openrouter/usage/`) was already extracted — not on
> count, but because it crosses a module boundary (clients -> persistence) and is a single orthogonal
> concern shared verbatim by every OpenRouter client.
