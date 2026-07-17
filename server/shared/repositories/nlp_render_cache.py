from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.nlp_render_cache import nlp_render_cache


class NlpRenderCacheRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, cache_key: str) -> str | None:
        stmt = select(nlp_render_cache.c.markup).where(
            nlp_render_cache.c.cache_key == cache_key
        )
        row = (await self.conn.execute(stmt)).first()
        return row.markup if row is not None else None

    async def put(self, cache_key: str, style: str, markup: str) -> None:
        stmt = pg_insert(nlp_render_cache).values(
            cache_key=cache_key, style=style, markup=markup
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["cache_key"])
        await self.conn.execute(stmt)
