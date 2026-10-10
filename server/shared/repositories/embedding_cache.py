from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.batching import insert_batches
from shared.db.tables.embedding_cache import embedding_cache
from shared.models.embedding_cache import NewEmbeddingCacheEntry


class EmbeddingCacheRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get_many(self, keys: list[str]) -> dict[str, list[float]]:
        if not keys:
            return {}
        stmt = select(embedding_cache.c.cache_key, embedding_cache.c.embedding).where(
            embedding_cache.c.cache_key.in_(keys)
        )
        rows = (await self.conn.execute(stmt)).all()
        return {row.cache_key: row.embedding for row in rows}

    async def put_many(self, entries: list[NewEmbeddingCacheEntry]) -> None:
        # Concurrent workers may compute the same key; the first writer wins and the
        # rest no-op.
        for batch in insert_batches(embedding_cache, entries):
            stmt = insert(embedding_cache).values(batch)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[embedding_cache.c.cache_key]
            )
            await self.conn.execute(stmt)
