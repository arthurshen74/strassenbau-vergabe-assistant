from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from api.main import app
from shared.db.unit_of_work import UnitOfWork

PROJECT_NAME = "project-name"
DE = "de"


def _body(query_text: str = "Wie heißt die Maßnahme?") -> dict[str, object]:
    return {
        "language": DE,
        "name": "Maßnahme",
        "description": "Titel der Maßnahme.",
        "query_text": query_text,
        "answer_instruction": "Nur den Titel.",
    }


@pytest_asyncio.fixture
async def client(conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    """AsyncClient whose reads and writes both run on the per-test connection."""

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


async def test_publish_list_and_history(client: AsyncClient) -> None:
    empty = await client.get("/rag-queries", params={"language": DE})
    assert empty.status_code == 200
    assert empty.json() == []

    first = await client.post(f"/rag-queries/{PROJECT_NAME}", json=_body("v1"))
    assert first.status_code == 201
    assert first.json()["version"] == 1

    listed = await client.get("/rag-queries", params={"language": DE})
    assert [(r["query_key"], r["version"]) for r in listed.json()] == [
        (PROJECT_NAME, 1)
    ]

    second = await client.post(f"/rag-queries/{PROJECT_NAME}", json=_body("v2"))
    assert second.json()["version"] == 2

    listed = await client.get("/rag-queries", params={"language": DE})
    assert [r["query_text"] for r in listed.json()] == ["v2"]

    history = await client.get(
        f"/rag-queries/{PROJECT_NAME}/history", params={"language": DE}
    )
    assert history.status_code == 200
    assert [r["version"] for r in history.json()] == [2, 1]


async def test_language_defaults_to_setting(client: AsyncClient) -> None:
    body = _body()
    del body["language"]
    created = await client.post(f"/rag-queries/{PROJECT_NAME}", json=body)
    assert created.status_code == 201
    assert created.json()["language"] == DE

    listed = await client.get("/rag-queries")
    assert len(listed.json()) == 1


async def test_other_language_is_absent(client: AsyncClient) -> None:
    await client.post(f"/rag-queries/{PROJECT_NAME}", json=_body())
    listed = await client.get("/rag-queries", params={"language": "en"})
    assert listed.json() == []


async def test_unknown_key_422(client: AsyncClient) -> None:
    resp = await client.post("/rag-queries/project-unknown", json=_body())
    assert resp.status_code == 422


async def test_empty_query_text_422(client: AsyncClient) -> None:
    resp = await client.post(f"/rag-queries/{PROJECT_NAME}", json=_body(""))
    assert resp.status_code == 422


async def test_invalid_language_422(client: AsyncClient) -> None:
    body = _body()
    body["language"] = "DEU"
    resp = await client.post(f"/rag-queries/{PROJECT_NAME}", json=body)
    assert resp.status_code == 422
