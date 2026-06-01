from __future__ import annotations

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.prompt_versions import prompt_versions
from shared.models.enums import PromptType
from shared.models.prompt_version import NewPromptVersion, PromptVersion

# Two writers racing on the same prompt_type can read the same max(version) and
# collide on the (prompt_type, version) unique; retry a handful of times before
# giving up so a genuine deadlock can't loop forever.
_MAX_VERSION_ASSIGN_ATTEMPTS = 5


class PromptVersionRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewPromptVersion) -> PromptVersion:
        """Append an immutable version, auto-assigning the next integer for the
        prompt_type. The insert runs in a savepoint so a unique collision under
        concurrency rolls back just the attempt and recomputes the version."""
        values = new.model_dump()
        for _ in range(_MAX_VERSION_ASSIGN_ATTEMPTS):
            next_version = (
                await self.conn.execute(
                    select(func.coalesce(func.max(prompt_versions.c.version), 0) + 1)
                    .where(prompt_versions.c.prompt_type == new.prompt_type)
                )
            ).scalar_one()
            try:
                async with self.conn.begin_nested():
                    row = (
                        await self.conn.execute(
                            insert(prompt_versions)
                            .values(**values, version=next_version)
                            .returning(prompt_versions)
                        )
                    ).mappings().one()
                return PromptVersion.model_validate(dict(row))
            except IntegrityError:
                continue
        raise RuntimeError(
            f"could not assign a version for prompt_type={new.prompt_type} "
            f"after {_MAX_VERSION_ASSIGN_ATTEMPTS} attempts"
        )

    async def get_by_type_and_version(
        self, prompt_type: PromptType, version: int
    ) -> PromptVersion | None:
        stmt = select(prompt_versions).where(
            prompt_versions.c.prompt_type == prompt_type,
            prompt_versions.c.version == version,
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return PromptVersion.model_validate(dict(row)) if row else None

    async def get_latest(self, prompt_type: PromptType) -> PromptVersion | None:
        stmt = (
            select(prompt_versions)
            .where(prompt_versions.c.prompt_type == prompt_type)
            .order_by(prompt_versions.c.version.desc())
            .limit(1)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return PromptVersion.model_validate(dict(row)) if row else None

    async def list_by_type(self, prompt_type: PromptType) -> list[PromptVersion]:
        stmt = (
            select(prompt_versions)
            .where(prompt_versions.c.prompt_type == prompt_type)
            .order_by(prompt_versions.c.version)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [PromptVersion.model_validate(dict(r)) for r in rows]
