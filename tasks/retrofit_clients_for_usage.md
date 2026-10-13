# Retrofit OpenRouter clients for usage & cost tracking

This brief is self-contained. It explains how the OpenRouter usage-tracking feature works and gives a
step-by-step recipe to wire it into each OpenRouter client. The embeddings and llm clients are already
done (use them as worked references); the rerank client is not built yet and adopts the same contract when
it is.

## Why

Every OpenRouter call (chat, embeddings, rerank) is billed, and OpenRouter returns the cost and token
counts in the response `usage` object. We capture that on every call so cost can be reported per project,
per ingest job, and per prompt. The clients previously discarded `usage`.

## How it works

One shared module owns the cross-cutting concern: `server/shared/clients/openrouter/usage/`.

- **`UsageEvent`** (`usage/parser.py`) — a Pydantic DTO a client hands to a sink. Decoupled from
  persistence. All metric fields are nullable (the three endpoints return different shapes).
- **`parse_usage(body, *, operation, model, project_uuid=None, ingest_job_uuid=None,
  chat_prompt_type=None, chat_prompt_version=None)`** — extracts the `usage` object into a `UsageEvent`.
  Defensive: an absent metric is `None`; `cost` (a JSON float) is converted via `Decimal(str(cost))`.
  Raises `MissingUsageError` if the body has no `usage` object, `MalformedUsageError` if a present field is
  non-numeric. `request_id` is read from the top-level `body["id"]`.
- **`UsageSink`** Protocol (`usage/sinks.py`) with `async emit(event)`:
  - `LoggingUsageSink` — one structured log line; the **default** sink (works offline and in tests).
  - `DatabaseUsageSink(engine)` — persists to the `openrouter_usage` table. It owns its own `AsyncEngine`
    and writes each event in its **own** short `engine.begin()` transaction, deliberately bypassing any
    caller `UnitOfWork`: the cost was really incurred, so it must survive a business-transaction rollback.
- Persistence: `openrouter_usage` table, `OpenRouterUsage`/`NewOpenRouterUsage` models,
  `OpenRouterUsageRepository` (registered on the `UnitOfWork` for reads).

### The three usage shapes (authoritative, from the OpenRouter OpenAPI specs)

| Field | Chat | Embeddings | Rerank |
| --- | :-: | :-: | :-: |
| `prompt_tokens` | yes | yes | — |
| `completion_tokens` | yes | — | — |
| `total_tokens` | yes | yes | yes |
| `cost` (credits == USD) | yes | yes | yes |
| `cached_tokens` (`prompt_tokens_details`) | yes | — | — |
| `reasoning_tokens` (`completion_tokens_details`) | yes | — | — |
| `search_units` (Cohere billing) | — | — | yes |

`cost` is normally present but is recorded null (with a warning) on the rare response that omits it.

## Client contract (every OpenRouter client follows this)

1. `__init__` accepts `usage_sink: UsageSink | None = None`, defaulting to `LoggingUsageSink()`.
2. Capture the response body once (`body = response.json()`) after `raise_for_status()`.
3. Call a guarded `_emit_usage(body, ...)` that wraps `parse_usage` + `sink.emit` in `try/except Exception`,
   logs once, and continues — **usage recording must never fail the primary call**. No emit happens when
   `raise_for_status()` itself raises (transport failure → no usable body).
4. Emit exactly once per call; hold no per-call usage state on the instance (concurrency safety — the
   worker runs many calls concurrently).
5. Reuse the SCREAMING_SNAKE field constants in `usage/parser.py`; never re-type `"usage"`/`"cost"`.
6. Return types are unchanged (sink injection, not return-value).

## Worked reference: embeddings (`clients/embeddings/client.py`, DONE)

```python
def __init__(self, client=None, usage_sink: UsageSink | None = None) -> None:
    ...
    self._usage_sink = usage_sink or LoggingUsageSink()

async def embed(self, texts, *, project_uuid=None, ingest_job_uuid=None) -> list[list[float]]:
    ...
    body = response.json()                 # captured once
    # ... dimension validation ...
    await self._emit_usage(body, project_uuid, ingest_job_uuid)
    return vectors

async def _emit_usage(self, body, project_uuid, ingest_job_uuid) -> None:
    try:
        event = parse_usage(body, operation=UsageOperation.EMBEDDING,
                            model=settings.embedding_model,
                            project_uuid=project_uuid, ingest_job_uuid=ingest_job_uuid)
        if event.cost is None:
            logger.warning("OpenRouter usage missing cost for model %s", event.model)
        await self._usage_sink.emit(event)
    except Exception:
        logger.exception("Failed to record embeddings usage; continuing")
```

## LLM / chat (`clients/llm/client.py`, DONE)

Same shape, with `UsageOperation.CHAT` and two specifics:

- `chat()` (and both `@overload`s) take optional `chat_prompt_type`/`chat_prompt_version` (caller-supplied
  from the prompt registry / `PromptVersion` system) plus `project_uuid`/`ingest_job_uuid`; they flow into
  `parse_usage`. `multi_query()` leaves them None (system-prompt-in-code, not a stored `PromptVersion`).
- **Emit before the refusal/truncation checks.** A content-filtered or `finish_reason=length` response is a
  billed 200, so emit usage right after `raise_for_status()` and *before* `chat()` raises `RefusalError` /
  `OutputTruncatedError`. `request_id` comes from `body["id"]`; `cached_tokens`/`reasoning_tokens` from the
  `*_tokens_details` objects.

## Rerank (NOT yet built — do this when the rerank call is added)

Rerank is config-only today (`settings.openrouter_api_url_rerank`, `settings.cross_encoder_model`); the
SearchClient is pure Elasticsearch and makes no OpenRouter call. When the rerank OpenRouter call is built
(a method on `LLMClient` or a small dedicated client):

1. Follow the contract above with `UsageOperation.RERANK`.
2. Rerank has **no** `prompt_tokens`/`completion_tokens` (leave both None) and populates `search_units` +
   `total_tokens` + `cost`. `request_id` is the top-level ORID `id`. `chat_prompt_*` stay None.
3. Wire it into the retrieval phase that performs reranking.

## Wiring the DB sink in production

The default sink is `LoggingUsageSink`. To persist, construct `DatabaseUsageSink(engine)` (reusing the
app/worker `AsyncEngine` from `app.state.engine`) and pass it as `usage_sink=` when the client is
instantiated at API/worker startup. (Client instantiation at startup is owned by the consuming wave.)

## Verification per client

- Unit (mocked `httpx.MockTransport`): a successful response emits one `UsageEvent` with the expected
  tokens/cost and `request_id`; a missing `usage.cost` → `cost=None` + warning; a missing `usage` object →
  primary result still returned and **no** emit; a raising stub sink does not break the call; no emit on a
  non-2xx response. For chat: usage is emitted even on refusal/truncation, before the raise.
- Repository integration (`tests/integration/repositories/test_openrouter_usage_repository.py`): round-trip
  `add`/`get`, enum coercion, `Decimal` precision, `list_by_*` filtering, `DatabaseUsageSink`
  own-transaction write.
- Live (gated on `OPENROUTER_LIVE_TEST=1`): a real call yields a `UsageEvent` with non-null `cost` and
  `total_tokens`.
