from __future__ import annotations

from sqlalchemy import func, insert, literal, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.rag_query_versions import rag_query_versions
from shared.models.enums import ProjectInfoQuery
from shared.models.rag_query import NewRagQueryVersion, RagQueryVersion


class RagQueryVersionRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewRagQueryVersion) -> RagQueryVersion:
        """Append an immutable version, assigning the next integer for the
        (query_key, language) in the same INSERT ... SELECT. A concurrent publish that
        still collides on the unique raises IntegrityError."""
        values = new.model_dump()
        next_version = select(
            *(literal(v).label(k) for k, v in values.items()),
            (func.coalesce(func.max(rag_query_versions.c.version), 0) + 1).label(
                "version"
            ),
        ).where(
            rag_query_versions.c.query_key == new.query_key,
            rag_query_versions.c.language == new.language,
        )
        stmt = (
            insert(rag_query_versions)
            .from_select([*values, "version"], next_version)
            .returning(rag_query_versions)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return RagQueryVersion.model_validate(dict(row))

    async def get_latest(
        self, query_key: ProjectInfoQuery, language: str
    ) -> RagQueryVersion | None:
        stmt = (
            select(rag_query_versions)
            .where(
                rag_query_versions.c.query_key == query_key,
                rag_query_versions.c.language == language,
            )
            .order_by(rag_query_versions.c.version.desc())
            .limit(1)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return RagQueryVersion.model_validate(dict(row)) if row else None

    async def latest_all(self, language: str) -> list[RagQueryVersion]:
        """Latest version of every key that has one in `language`, ordered by key."""
        stmt = (
            select(rag_query_versions)
            .distinct(rag_query_versions.c.query_key)
            .where(rag_query_versions.c.language == language)
            .order_by(
                rag_query_versions.c.query_key,
                rag_query_versions.c.version.desc(),
            )
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [RagQueryVersion.model_validate(dict(r)) for r in rows]

    async def history(
        self, query_key: ProjectInfoQuery, language: str
    ) -> list[RagQueryVersion]:
        """Every version of one key in `language`, newest first."""
        stmt = (
            select(rag_query_versions)
            .where(
                rag_query_versions.c.query_key == query_key,
                rag_query_versions.c.language == language,
            )
            .order_by(rag_query_versions.c.version.desc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [RagQueryVersion.model_validate(dict(r)) for r in rows]
