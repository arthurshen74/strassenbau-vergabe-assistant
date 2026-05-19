from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.prompt_versions import prompt_versions
from shared.db.tables.prompts import prompts
from shared.domain.prompt import NewPrompt, Prompt
from shared.domain.prompt_version import NewPromptVersion, PromptVersion


class PromptRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, prompt_uuid: UUID) -> Prompt | None:
        row = (
            await self.conn.execute(
                select(prompts).where(prompts.c.prompt_uuid == prompt_uuid)
            )
        ).mappings().first()
        return Prompt.model_validate(dict(row)) if row else None

    async def get_by_slug(self, slug: str) -> Prompt | None:
        row = (
            await self.conn.execute(
                select(prompts).where(prompts.c.slug == slug)
            )
        ).mappings().first()
        return Prompt.model_validate(dict(row)) if row else None

    async def list(
        self,
        *,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Prompt]:
        stmt = select(prompts)
        if not include_archived:
            stmt = stmt.where(prompts.c.is_archived.is_(False))
        stmt = stmt.order_by(prompts.c.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Prompt.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewPrompt) -> Prompt:
        stmt = insert(prompts).values(**new.model_dump()).returning(prompts)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Prompt.model_validate(dict(row))

    async def update(self, prompt_uuid: UUID, **changes: Any) -> Prompt | None:
        if not changes:
            return await self.get(prompt_uuid)
        stmt = (
            update(prompts)
            .where(prompts.c.prompt_uuid == prompt_uuid)
            .values(**changes)
            .returning(prompts)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Prompt.model_validate(dict(row)) if row else None

    async def archive(self, prompt_uuid: UUID) -> Prompt | None:
        return await self.update(prompt_uuid, is_archived=True)

    async def unarchive(self, prompt_uuid: UUID) -> Prompt | None:
        return await self.update(prompt_uuid, is_archived=False)

    async def get_version(
        self, prompt_uuid: UUID, version: int
    ) -> PromptVersion | None:
        row = (
            await self.conn.execute(
                select(prompt_versions).where(
                    and_(
                        prompt_versions.c.prompt_uuid == prompt_uuid,
                        prompt_versions.c.version == version,
                    )
                )
            )
        ).mappings().first()
        return PromptVersion.model_validate(dict(row)) if row else None

    async def get_version_by_slug(
        self, slug: str, version: int | Literal["latest"] = "latest"
    ) -> PromptVersion | None:
        stmt = (
            select(prompt_versions)
            .join(prompts, prompts.c.prompt_uuid == prompt_versions.c.prompt_uuid)
            .where(prompts.c.slug == slug)
        )
        if version == "latest":
            stmt = stmt.order_by(prompt_versions.c.version.desc()).limit(1)
        else:
            stmt = stmt.where(prompt_versions.c.version == version)
        row = (await self.conn.execute(stmt)).mappings().first()
        return PromptVersion.model_validate(dict(row)) if row else None

    async def list_versions(self, prompt_uuid: UUID) -> Sequence[PromptVersion]:
        stmt = (
            select(prompt_versions)
            .where(prompt_versions.c.prompt_uuid == prompt_uuid)
            .order_by(prompt_versions.c.version.asc())
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [PromptVersion.model_validate(dict(r)) for r in rows]

    async def add_version(
        self, prompt_uuid: UUID, new: NewPromptVersion
    ) -> PromptVersion:
        next_version = (
            await self.conn.execute(
                select(func.coalesce(func.max(prompt_versions.c.version), 0) + 1).where(
                    prompt_versions.c.prompt_uuid == prompt_uuid
                )
            )
        ).scalar_one()
        stmt = (
            insert(prompt_versions)
            .values(
                prompt_uuid=prompt_uuid,
                version=next_version,
                **new.model_dump(),
            )
            .returning(prompt_versions)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return PromptVersion.model_validate(dict(row))
