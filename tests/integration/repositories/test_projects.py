from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.projects import projects
from shared.models.project import NewProject
from shared.repositories.projects import ProjectRepository


def _new(vergabe_id: str = "VG-1") -> NewProject:
    return NewProject(
        vergabe_id=vergabe_id,
        project_name="B247 OD Test",
        project_description="Test tender",
        vergabestelle="LRA Test",
    )


async def test_add_and_get(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    created = await repo.add(_new())
    fetched = await repo.get(created.project_uuid)
    assert fetched is not None
    assert fetched.project_uuid == created.project_uuid
    assert fetched.project_name == "B247 OD Test"


async def test_get_missing_returns_none(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    assert await repo.get(uuid4()) is None


async def test_list_ordered_by_created_at(conn: AsyncConnection) -> None:
    # Explicit created_at so the order_by is actually exercised (server_default now()
    # is constant within a transaction).
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = []
    for offset, name in ((2, "third"), (0, "first"), (1, "second")):
        pid = (
            await conn.execute(
                insert(projects)
                .values(
                    vergabe_id=f"ORD-{name}",
                    project_name=name,
                    project_description="d",
                    vergabestelle="V",
                    created_at=base + timedelta(minutes=offset),
                )
                .returning(projects.c.project_uuid)
            )
        ).scalar_one()
        ids.append(pid)

    repo = ProjectRepository(conn)
    listed = [p for p in await repo.list() if p.project_uuid in set(ids)]
    assert [p.project_name for p in listed] == ["first", "second", "third"]


async def test_update_returns_changed(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    created = await repo.add(_new())
    updated = await repo.update(created.project_uuid, project_name="Renamed")
    assert updated is not None
    assert updated.project_name == "Renamed"
    assert updated.vergabestelle == created.vergabestelle


async def test_delete_removes(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    created = await repo.add(_new())
    await repo.delete(created.project_uuid)
    assert await repo.get(created.project_uuid) is None
