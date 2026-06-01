# Abstraction Candidates

Tracked duplication that is NOT yet worth extracting (see `CLAUDE.local.md` "DRY (and when not)").
Duplicate freely up to three similar instances. **Longshot** = 2 similar instances; **Good Bet** = 3.
Extract on the fourth instance, or when the duplication crosses a module boundary. Remove an entry once
its extraction is complete.

## Longshots (2 instances)

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
