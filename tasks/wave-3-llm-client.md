# Wave 3 — OpenRouter LLM transport

Read `tasks/README.md` first. Independent of the Postgres waves — depends only on
`server/shared/config.py` (complete). `httpx` is already a dependency. Do **not** add the `anthropic`
or `openai` SDK paths here (reserved for `eval/`).

## Goal

A single OpenRouter transport in `server/shared/clients/llm/` that all LLM calls in the system go
through. The package `__init__` must re-export `LLMClient`, `RefusalError`, `OutputTruncatedError`
(it is currently a `__all__ = []` stub).

## Files

- `server/shared/clients/llm/client.py` — `LLMClient` + the two error types.
- `server/shared/clients/llm/prompt_registry.py` — `PromptType → (Pydantic output model | None)` map.
- `server/shared/clients/llm/__init__.py` — re-export.
- `tests/unit/llm/test_client.py`, `tests/unit/llm/test_prompt_registry.py` (mock `httpx`, no live key).

## Spec

- Build an `httpx.AsyncClient` (or per-call) targeting `settings.openrouter_api_url_chat`, auth
  `Authorization: Bearer {settings.openrouter_api_key}`. Model is a slug passed by the caller
  (e.g. `settings.multi_query_model`).
- **Structured-output chat:** a method that takes messages + an optional Pydantic output model and,
  when given one, requests JSON-schema-constrained output (OpenRouter `response_format` /
  `json_schema`) and returns a validated instance. When no model is given, return the raw text.
- **`RefusalError`** when the model refuses; **`OutputTruncatedError`** when the finish reason is
  length/truncation. These are the two failure modes callers must distinguish.
- **Multi-query helper** for RETRIEVAL: generate `settings.multi_query_n` query variants using
  `settings.multi_query_model`; return `list[str]`.
- **Prompt registry (schema-in-code):** map each `PromptType` (`server/shared/models/enums.py`) to an
  optional Pydantic output model. **Not every type has one** — a missing entry means free-form output,
  no structured-output enforcement. Expose a lookup that returns `None` cleanly for unmapped types.
  (Concrete per-type schemas are defined in their feature phases; here, wire the mechanism and leave the
  map mostly empty/with placeholders.)
- Optional: a `rerank` method against `settings.openrouter_api_url_rerank` + `settings.cross_encoder_model`
  — include only if trivial; otherwise leave for the retrieval phase.

## Conventions

`from __future__ import annotations`; full type hints; `ConfigDict(extra="forbid")` on any DTOs; one log
at the boundary on failure, not inside helpers; validate the LLM response via the Pydantic schema
(boundary validation).

## Verification

`pytest tests/unit/llm -q` with `httpx` mocked (e.g. `respx` is NOT a dep — use
`unittest.mock`/monkeypatched transport or `httpx.MockTransport`): structured parse path returns a
validated model; refusal finish → `RefusalError`; length finish → `OutputTruncatedError`; multi-query
returns N strings; registry returns `None` for an unmapped `PromptType` and the model for a mapped one.

## Done when

`from shared.clients.llm import LLMClient, RefusalError, OutputTruncatedError` works and unit tests pass.

## Update: OpenRouter usage tracking (added later)

`LLMClient` now records token usage and cost on every `chat()` call. The constructor takes an optional
`usage_sink: UsageSink | None`; `chat()` takes optional `chat_prompt_type`/`chat_prompt_version`/
`project_uuid`/`ingest_job_uuid` attribution and emits a `UsageEvent` (operation `CHAT`) before the
refusal/truncation checks (a filtered/truncated 200 is still billed). See
`tasks/retrofit_clients_for_usage.md` for the full mechanism and contract.
