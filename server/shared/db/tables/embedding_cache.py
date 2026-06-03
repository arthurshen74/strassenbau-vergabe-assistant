from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, Table, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from shared.db.metadata import metadata

# cache_key is a SHA-256 hex of (embedding_model, embedding_dim, text); embedding holds the
# vector as a JSON array of floats. Keying on model+dim means a model or dimension change is a
# clean miss rather than a stale hit, so no separate invalidation is needed.
embedding_cache = Table(
    "embedding_cache",
    metadata,
    Column("cache_key", Text, primary_key=True),
    Column("model", Text, nullable=False),
    Column("dim", Integer, nullable=False),
    Column("embedding", JSONB, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
