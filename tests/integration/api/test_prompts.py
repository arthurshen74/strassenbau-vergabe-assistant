from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from api.main import app
from shared.db.unit_of_work import UnitOfWork

DISPATCHER = "dispatcher"
PROJECT_CHAT = "project_chat"


def _create_body(model_name: str = "anthropic/claude-sonnet-4.6") -> dict[str, object]:
    return {
        "prompt_type": DISPATCHER,
        "model_name": model_name,
        "system_prompt": "You dispatch.",
        "temperature": 0.0,
    }


@pytest_asyncio.fixture
async def client(conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    """AsyncClient whose reads and writes both run on the per-test connection, so
    every change rolls back with the `conn` fixture and tests stay isolated."""

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


async def test_create_assigns_incrementing_versions(client: AsyncClient) -> None:
    first = await client.post("/prompts", json=_create_body())
    assert first.status_code == 201
    assert first.json()["version"] == 1

    second = await client.post("/prompts", json=_create_body())
    assert second.status_code == 201
    assert second.json()["version"] == 2


async def test_get_latest_and_pinned(client: AsyncClient) -> None:
    await client.post("/prompts", json=_create_body())
    await client.post("/prompts", json=_create_body())

    latest = await client.get(f"/prompts/{DISPATCHER}/latest")
    assert latest.status_code == 200
    assert latest.json()["version"] == 2

    pinned = await client.get(f"/prompts/{DISPATCHER}/1")
    assert pinned.status_code == 200
    assert pinned.json()["version"] == 1


async def test_list_returns_versions_in_order(client: AsyncClient) -> None:
    await client.post("/prompts", json=_create_body())
    await client.post("/prompts", json=_create_body())

    listed = await client.get(f"/prompts/{DISPATCHER}")
    assert listed.status_code == 200
    assert [v["version"] for v in listed.json()] == [1, 2]


async def test_404_on_missing_version(client: AsyncClient) -> None:
    await client.post("/prompts", json=_create_body())
    missing = await client.get(f"/prompts/{DISPATCHER}/99")
    assert missing.status_code == 404


async def test_404_on_latest_when_none(client: AsyncClient) -> None:
    missing = await client.get(f"/prompts/{PROJECT_CHAT}/latest")
    assert missing.status_code == 404
