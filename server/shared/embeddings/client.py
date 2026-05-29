from __future__ import annotations


class DirectOpenRouterEmbeddings:
    """OpenRouter embeddings over the OpenAI-compatible endpoint.

    Implements the `langchain_core.embeddings.Embeddings` interface
    (`embed_documents` / `embed_query`, sync per that contract), wrapping
    `openai.OpenAI(base_url="https://openrouter.ai/api/v1")` with
    `model=settings.embedding_model` and `dimensions=settings.embedding_dim`
    (`OPENROUTER_API_KEY`). Ingest and retrieval share one instance so document and
    query vectors live in the same space. See docs/DATA_MODEL.md §11.8, docs/LV_INGEST.md §9.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError
