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

> Note: the usage parser + sink (`server/shared/clients/openrouter/usage/`) was already extracted — not on
> count, but because it crosses a module boundary (clients -> persistence) and is a single orthogonal
> concern shared verbatim by every OpenRouter client.
