from __future__ import annotations


class OpenRouterEmbeddings:
    """Async OpenRouter embeddings over the OpenAI-compatible endpoint.

    Thin transport: text -> vector, store-agnostic. Wraps
    `openai.AsyncOpenAI(base_url="https://openrouter.ai/api/v1")` with
    `model=settings.embedding_model` and `dimensions=settings.embedding_dim`
    (`OPENROUTER_API_KEY`). Ingest and retrieval share one instance so document and
    query vectors live in the same space. Storage and similarity query belong to
    `GraphClient`, not here. See docs/DATA_MODEL.md §11.8, docs/LV_INGEST.md §9.
    """

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError
