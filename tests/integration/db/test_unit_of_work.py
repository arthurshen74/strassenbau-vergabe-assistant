"""Unit of Work transaction semantics against real Postgres.

These use the session `engine` directly (not the rollback-per-test `conn` fixture)
because the point is to prove the UoW's own transaction commits and rolls back. The
commit case cleans up after itself so it doesn't leak into the shared test database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.db.tables.documents import documents
from shared.db.tables.projects import projects
from shared.db.unit_of_work import unit_of_work
from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.project import NewProject

_COMMIT_MARKER = "UOW-COMMIT-MARKER"
_ROLLBACK_MARKER = "UOW-ROLLBACK-MARKER"


async def test_multi_repo_write_commits_atomically(engine: AsyncEngine) -> None:
    project_uuid = None
    try:
        async with unit_of_work(engine) as uow:
            project = await uow.projects.add(
                NewProject(
                    vergabe_id=_COMMIT_MARKER,
                    project_name="UoW commit",
                    project_description="d",
                    vergabestelle="V",
                )
            )
            await uow.documents.add(
                NewDocument(
                    project_uuid=project.project_uuid,
                    document_type=DocumentType.LV_DOCUMENT,
                    file_name="lv.pdf",
                    number_of_pages=3,
                )
            )
        project_uuid = project.project_uuid

        # A fresh connection only sees committed rows.
        async with engine.connect() as conn:
            found_project = (
                await conn.execute(
                    select(projects.c.project_uuid).where(
                        projects.c.project_uuid == project_uuid
                    )
                )
            ).first()
            doc_count = len(
                (
                    await conn.execute(
                        select(documents.c.document_uuid).where(
                            documents.c.project_uuid == project_uuid
                        )
                    )
                ).all()
            )
        assert found_project is not None
        assert doc_count == 1
    finally:
        if project_uuid is not None:
            async with engine.begin() as conn:
                await conn.execute(
                    projects.delete().where(projects.c.project_uuid == project_uuid)
                )


async def test_exception_rolls_everything_back(engine: AsyncEngine) -> None:
    with pytest.raises(RuntimeError):
        async with unit_of_work(engine) as uow:
            await uow.projects.add(
                NewProject(
                    vergabe_id=_ROLLBACK_MARKER,
                    project_name="UoW rollback",
                    project_description="d",
                    vergabestelle="V",
                )
            )
            raise RuntimeError("boom")

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(projects.c.project_uuid).where(
                    projects.c.vergabe_id == _ROLLBACK_MARKER
                )
            )
        ).all()
    assert rows == []
