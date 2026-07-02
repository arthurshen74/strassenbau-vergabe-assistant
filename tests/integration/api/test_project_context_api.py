from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import (
    get_connection,
    get_embeddings,
    get_engine,
    get_llm_client,
    get_reranker,
    get_search,
    get_uow,
)
from api.main import app
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.project import NewProject
from shared.repositories.projects import ProjectRepository


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock mode: resolve uses fixtures + the mock geocoder, so the RetrievalService/LLM deps
    # (overridden to None below) are never exercised.
    monkeypatch.setattr(settings, "calculator_mock", True)


@pytest_asyncio.fixture
async def client(conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    async def _connection() -> AsyncIterator[AsyncConnection]:
        yield conn

    async def _uow() -> AsyncIterator[UnitOfWork]:
        yield UnitOfWork(conn)

    app.dependency_overrides[get_connection] = _connection
    app.dependency_overrides[get_uow] = _uow
    for dep in (get_engine, get_llm_client, get_embeddings, get_search, get_reranker):
        app.dependency_overrides[dep] = lambda: None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def _project(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-PCAPI",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    return project.project_uuid


async def test_context_lifecycle(conn: AsyncConnection, client: AsyncClient) -> None:
    project_uuid = await _project(conn)

    empty = await client.get(f"/projects/{project_uuid}/context")
    assert empty.status_code == 200
    assert empty.json()["vorhanden"] is False

    resolved = await client.post(f"/projects/{project_uuid}/context/resolve")
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["vorhanden"] is True
    assert body["baustelle_location"] == "Baustelle L 101, Nordhausen"
    assert body["strip_length_m"] == "5100"
    assert body["entfernung_deponie_km"] is not None

    updated = await client.put(
        f"/projects/{project_uuid}/context", json={"fraesgut_klasse": "2"}
    )
    assert updated.status_code == 200
    assert updated.json()["fraesgut_klasse"] == "2"

    history = await client.get(f"/projects/{project_uuid}/context/history")
    assert history.status_code == 200
    entries = {h["variable_name"]: h["versionen"] for h in history.json()}
    assert [v["version"] for v in entries["fraesgut_klasse"]] == [1, 2]
    assert entries["fraesgut_klasse"][1]["quelle"] == "hitl"


async def test_context_clear(conn: AsyncConnection, client: AsyncClient) -> None:
    project_uuid = await _project(conn)
    await client.post(f"/projects/{project_uuid}/context/resolve")

    cleared = await client.delete(f"/projects/{project_uuid}/context")
    assert cleared.status_code == 200
    assert cleared.json()["vorhanden"] is False

    after = await client.get(f"/projects/{project_uuid}/context")
    assert after.json()["vorhanden"] is False


async def test_context_404_for_unknown_project(client: AsyncClient) -> None:
    missing = UUID("00000000-0000-0000-0000-0000000000ff")
    resp = await client.get(f"/projects/{missing}/context")
    assert resp.status_code == 404


async def test_context_map_returns_png(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api.routes import project_contexts

    async def _fake_png(address: str, *, zoom: int, **_kw: object) -> bytes:
        assert "," in address                                  # centered on "lat,lon"
        return b"PNGBYTES"

    monkeypatch.setattr(project_contexts, "fetch_static_map_png", _fake_png)
    resp = await client.get(
        "/projects/00000000-0000-0000-0000-0000000000aa/context/map",
        params={"lat": "51.42", "lon": "10.81"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == b"PNGBYTES"


async def test_context_map_502_without_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "google_static_maps_api_key", None)
    resp = await client.get(
        "/projects/00000000-0000-0000-0000-0000000000aa/context/map",
        params={"lat": "51.42", "lon": "10.81"},
    )
    assert resp.status_code == 502


async def test_context_geocode_returns_coords(client: AsyncClient) -> None:
    # Mock mode: the geocoder returns the fixture coordinate for any address (no network).
    resp = await client.get(
        "/projects/00000000-0000-0000-0000-0000000000aa/context/geocode",
        params={"address": "L 151 Blankenheim"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["breitengrad"] == "51.42"
    assert body["laengengrad"] == "10.81"


async def test_context_route_map_returns_png(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.routes import project_contexts

    async def _fake_route_png(origin: str, dest: str, polyline: str, **_kw: object) -> bytes:
        assert "," in origin and "," in dest                   # both "lat,lon"
        return b"ROUTEPNG"

    monkeypatch.setattr(project_contexts, "fetch_route_map_png", _fake_route_png)
    resp = await client.get(
        "/projects/00000000-0000-0000-0000-0000000000aa/context/route-map",
        params={"origin_lat": "51.42", "origin_lon": "10.81",
                "dest_lat": "51.47", "dest_lon": "11.30"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == b"ROUTEPNG"
