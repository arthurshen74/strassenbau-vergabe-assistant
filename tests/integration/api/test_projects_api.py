from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_storage, get_uow
from api.main import app
from shared.db.unit_of_work import UnitOfWork
from shared.models.project import NewProject
from shared.repositories.projects import ProjectRepository


@pytest_asyncio.fixture
async def client(conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    async def _connection() -> AsyncIterator[AsyncConnection]:
        yield conn

    async def _uow() -> AsyncIterator[UnitOfWork]:
        yield UnitOfWork(conn)

    app.dependency_overrides[get_connection] = _connection
    app.dependency_overrides[get_uow] = _uow
    # The writable service wants a StorageClient, which create/update never touch.
    app.dependency_overrides[get_storage] = lambda: None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def test_create_with_name_only(client: AsyncClient) -> None:
    resp = await client.post("/projects", json={"project_name": "B247 OD"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["project_name"] == "B247 OD"
    assert body["vergabe_id"] is None
    assert body["massnahmenummer"] is None
    assert body["bauleistung"] is None


async def test_create_rejects_empty_name(client: AsyncClient) -> None:
    resp = await client.post("/projects", json={"project_name": ""})
    assert resp.status_code == 422


async def test_patch_updates_only_sent_fields(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project = await ProjectRepository(conn).add(
        NewProject(project_name="P", vergabe_id="VG-1", vergabestelle="LRA")
    )
    resp = await client.patch(
        f"/projects/{project.project_uuid}",
        json={"massnahmenummer": "M-1", "bauleistung": "Deckenerneuerung"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["massnahmenummer"] == "M-1"
    assert body["bauleistung"] == "Deckenerneuerung"
    assert body["vergabe_id"] == "VG-1"
    assert body["vergabestelle"] == "LRA"


async def test_patch_null_clears_field(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project = await ProjectRepository(conn).add(
        NewProject(project_name="P", location="Erfurt")
    )
    resp = await client.patch(
        f"/projects/{project.project_uuid}", json={"location": None}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["location"] is None


async def test_patch_rejects_empty_name_and_unknown_field(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project = await ProjectRepository(conn).add(NewProject(project_name="P"))
    url = f"/projects/{project.project_uuid}"
    assert (await client.patch(url, json={"project_name": ""})).status_code == 422
    assert (await client.patch(url, json={"surprise": "x"})).status_code == 422


async def test_patch_missing_project_is_404(client: AsyncClient) -> None:
    resp = await client.patch(f"/projects/{uuid4()}", json={"location": "x"})
    assert resp.status_code == 404
