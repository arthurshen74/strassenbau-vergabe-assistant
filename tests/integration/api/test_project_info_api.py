from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from api.main import app
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.enums import IngestStatus
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
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def test_get_is_404_without_job(client: AsyncClient, conn: AsyncConnection) -> None:
    project = await ProjectRepository(conn).add(NewProject(project_name="P"))
    resp = await client.get(f"/projects/{project.project_uuid}/project-info")
    assert resp.status_code == 404


async def test_run_enqueues_then_returns_open_job(
    client: AsyncClient, conn: AsyncConnection
) -> None:
    project = await ProjectRepository(conn).add(NewProject(project_name="P"))
    url = f"/projects/{project.project_uuid}/project-info"

    first = await client.post(f"{url}/run", json={"overwrite": True})
    assert first.status_code == 202, first.text
    body = first.json()
    assert body["status"] == IngestStatus.QUEUED
    assert body["overwrite"] is True
    assert body["language"] == settings.project_info_language

    second = await client.post(f"{url}/run", json={"overwrite": False})
    assert second.status_code == 202
    assert second.json()["job_uuid"] == body["job_uuid"]

    latest = await client.get(url)
    assert latest.status_code == 200
    assert latest.json()["job_uuid"] == body["job_uuid"]


async def test_run_missing_project_is_404(client: AsyncClient) -> None:
    resp = await client.post(f"/projects/{uuid4()}/project-info/run", json={"overwrite": True})
    assert resp.status_code == 404
