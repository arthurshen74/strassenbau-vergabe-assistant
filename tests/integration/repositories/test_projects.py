from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.project import NewProject
from shared.repositories.projects import ProjectRepository


def _new() -> NewProject:
    return NewProject(
        project_id="VS-2026-0042",
        project_name="Autobahn A1 Brückensanierung",
        project_description="Repair of bridge spans on A1 between km 134 and 156.",
        vergabe_stelle="Autobahn GmbH des Bundes",
        project_start=date(2026, 6, 15),
        project_location="Niedersachsen",
    )


async def test_add_round_trips_all_fields(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    new = _new()
    created = await repo.add(new)

    assert created.project_uuid is not None
    assert created.project_id == new.project_id
    assert created.project_name == new.project_name
    assert created.project_description == new.project_description
    assert created.vergabe_stelle == new.vergabe_stelle
    assert created.project_start == new.project_start
    assert created.project_location == new.project_location
    assert created.created_at is not None
    assert created.updated_at is not None


async def test_get_returns_the_added_project(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    created = await repo.add(_new())
    fetched = await repo.get(created.project_uuid)
    assert fetched is not None
    assert fetched.project_uuid == created.project_uuid


async def test_get_missing_returns_none(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    result = await repo.get(uuid4())
    assert result is None


async def test_get_by_external_id_returns_project(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    created = await repo.add(_new())
    fetched = await repo.get_by_external_id(
        created.vergabe_stelle, created.project_id
    )
    assert fetched is not None
    assert fetched.project_uuid == created.project_uuid


async def test_get_by_external_id_missing_returns_none(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    result = await repo.get_by_external_id("Unknown Vergabestelle", "VS-9999-9999")
    assert result is None


async def test_unique_constraint_blocks_same_project_id_in_same_vergabestelle(
    conn: AsyncConnection,
) -> None:
    repo = ProjectRepository(conn)
    await repo.add(_new())
    with pytest.raises(IntegrityError):
        await repo.add(
            NewProject(
                project_id="VS-2026-0042",
                project_name="A different project, same ids",
                vergabe_stelle="Autobahn GmbH des Bundes",
                project_location="Anywhere",
            )
        )


async def test_same_project_id_allowed_across_different_vergabestellen(
    conn: AsyncConnection,
) -> None:
    repo = ProjectRepository(conn)
    a = await repo.add(_new())
    b = await repo.add(
        NewProject(
            project_id="VS-2026-0042",
            project_name="Same external id, different awarding authority",
            vergabe_stelle="DEGES",
            project_location="Berlin",
        )
    )
    assert a.project_uuid != b.project_uuid
    assert a.project_id == b.project_id


async def test_add_with_only_required_fields(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    minimal = NewProject(
        project_id="VS-2026-0001",
        project_name="Minimal",
        vergabe_stelle="Behörde",
        project_location="Berlin",
    )
    created = await repo.add(minimal)
    assert created.project_description is None
    assert created.project_start is None


async def test_list_returns_added_projects(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    a = await repo.add(
        NewProject(
            project_id="VS-A",
            project_name="A",
            vergabe_stelle="X",
            project_location="Y",
        )
    )
    b = await repo.add(
        NewProject(
            project_id="VS-B",
            project_name="B",
            vergabe_stelle="X",
            project_location="Y",
        )
    )
    listed = await repo.list()
    uuids = {p.project_uuid for p in listed}
    assert a.project_uuid in uuids
    assert b.project_uuid in uuids


async def test_update_changes_fields(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    created = await repo.add(_new())
    updated = await repo.update(created.project_uuid, project_name="Renamed")
    assert updated is not None
    assert updated.project_name == "Renamed"
    assert updated.project_uuid == created.project_uuid


async def test_update_missing_returns_none(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    result = await repo.update(uuid4(), project_name="ghost")
    assert result is None


async def test_delete_removes_the_row(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    created = await repo.add(_new())
    assert await repo.delete(created.project_uuid) is True
    assert await repo.get(created.project_uuid) is None


async def test_delete_missing_returns_false(conn: AsyncConnection) -> None:
    repo = ProjectRepository(conn)
    assert await repo.delete(uuid4()) is False
