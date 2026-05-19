from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.projects import projects
from shared.domain.project import NewProject, Project


class ProjectRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def get(self, project_id: UUID) -> Project | None:
        row = (
            await self.conn.execute(
                select(projects).where(projects.c.project_id == project_id)
            )
        ).mappings().first()
        return Project.model_validate(dict(row)) if row else None

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[Project]:
        stmt = (
            select(projects)
            .order_by(projects.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Project.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewProject) -> Project:
        stmt = insert(projects).values(**new.model_dump()).returning(projects)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Project.model_validate(dict(row))

    async def update(self, project_id: UUID, **changes: Any) -> Project | None:
        if not changes:
            return await self.get(project_id)
        stmt = (
            update(projects)
            .where(projects.c.project_id == project_id)
            .values(**changes)
            .returning(projects)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Project.model_validate(dict(row)) if row else None

    async def delete(self, project_id: UUID) -> bool:
        result = await self.conn.execute(
            delete(projects).where(projects.c.project_id == project_id)
        )
        return result.rowcount > 0
