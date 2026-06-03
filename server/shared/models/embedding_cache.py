from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class NewEmbeddingCacheEntry(BaseModel):
    """Create-model for one cached embedding. created_at assigned by the DB."""

    model_config = ConfigDict(extra="forbid")

    cache_key: str
    model: str
    dim: int
    embedding: list[float]
