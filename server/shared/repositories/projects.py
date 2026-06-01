from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.projects import projects
from shared.models.project import NewProject, Project


class ProjectRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def add(self, new: NewProject) -> Project:
        stmt = insert(projects).values(**new.model_dump()).returning(projects)
        row = (await self.conn.execute(stmt)).mappings().one()
        return Project.model_validate(dict(row))

    async def get(self, project_uuid: UUID) -> Project | None:
        stmt = select(projects).where(projects.c.project_uuid == project_uuid)
        row = (await self.conn.execute(stmt)).mappings().first()
        return Project.model_validate(dict(row)) if row else None

    async def list(self) -> list[Project]:
        stmt = select(projects).order_by(projects.c.created_at)
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Project.model_validate(dict(r)) for r in rows]

    async def update(self, project_uuid: UUID, **changes: Any) -> Project | None:
        if not changes:
            return await self.get(project_uuid)
        stmt = (
            update(projects)
            .where(projects.c.project_uuid == project_uuid)
            .values(**changes)
            .returning(projects)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Project.model_validate(dict(row)) if row else None

    async def delete(self, project_uuid: UUID) -> None:
        stmt = delete(projects).where(projects.c.project_uuid == project_uuid)
        await self.conn.execute(stmt)
