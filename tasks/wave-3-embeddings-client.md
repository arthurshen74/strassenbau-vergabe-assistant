# Wave 3 — Embeddings client

Read `tasks/README.md` first. Independent of other waves; depends on `server/shared/config.py`. Uses
`httpx` (already a dependency).

## Goal

`server/shared/clients/embeddings/client.py` — an OpenRouter embeddings client.

## Spec

- `httpx` to `settings.openrouter_api_url_embedding`, auth `Bearer {settings.openrouter_api_key}`,
  model `settings.embedding_model` (`openai/text-embedding-3-small`).
- Accept a batch (`list[str]`) and return `list[list[float]]`; each vector length must equal
  `settings.embedding_dim` (512). Validate/raise on mismatch (boundary validation).
- Re-export the client in `server/shared/clients/embeddings/__init__.py`.

## Conventions

`from __future__ import annotations`; full type hints; one boundary log on failure. The embedding model
name and dimension come from `settings` — do not hardcode them.

## Verification

`tests/unit/embeddings/test_client.py` with `httpx` mocked: batch in → vectors out; dimension assertion
fires on a wrong-length vector. (Optionally a live test gated on `OPENROUTER_API_KEY` being set.)

## Done when

Batch embedding returns correctly-dimensioned vectors and the unit test passes.
