from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from api.main import app


@pytest_asyncio.fixture
async def client(conn: AsyncConnection) -> AsyncIterator[AsyncClient]:
    async def _override() -> AsyncIterator[AsyncConnection]:
        yield conn

    app.dependency_overrides[get_connection] = _override
    app.dependency_overrides[get_uow] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _version_payload(**overrides) -> dict:
    base = dict(
        system_prompt="You are a helpful assistant.",
        model_provider="anthropic",
        model_id="claude-sonnet-4-6",
        api_key_ref="ANTHROPIC_API_KEY",
        temperature=0.0,
        max_tokens=1024,
    )
    base.update(overrides)
    return base


async def test_create_and_get_prompt(client: AsyncClient) -> None:
    r = await client.post(
        "/prompts", json={"slug": "extract_assertions", "description": "Extract"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "extract_assertions"
    assert body["is_archived"] is False

    r = await client.get("/prompts/extract_assertions")
    assert r.status_code == 200
    assert r.json()["slug"] == "extract_assertions"


async def test_create_duplicate_slug_conflicts(client: AsyncClient) -> None:
    await client.post("/prompts", json={"slug": "dupe"})
    r = await client.post("/prompts", json={"slug": "dupe"})
    assert r.status_code == 409


async def test_get_missing_prompt_404(client: AsyncClient) -> None:
    r = await client.get("/prompts/does_not_exist")
    assert r.status_code == 404


async def test_list_filters_archived(client: AsyncClient) -> None:
    await client.post("/prompts", json={"slug": "live"})
    await client.post("/prompts", json={"slug": "gone"})
    await client.patch("/prompts/gone", json={"is_archived": True})

    r = await client.get("/prompts")
    slugs = {p["slug"] for p in r.json()}
    assert "live" in slugs
    assert "gone" not in slugs

    r = await client.get("/prompts", params={"include_archived": True})
    slugs_all = {p["slug"] for p in r.json()}
    assert "gone" in slugs_all


async def test_patch_updates_description(client: AsyncClient) -> None:
    await client.post("/prompts", json={"slug": "patchme", "description": "old"})
    r = await client.patch("/prompts/patchme", json={"description": "new"})
    assert r.status_code == 200
    assert r.json()["description"] == "new"


async def test_create_and_list_versions(client: AsyncClient) -> None:
    await client.post("/prompts", json={"slug": "versioned"})
    r1 = await client.post("/prompts/versioned/versions", json=_version_payload())
    r2 = await client.post(
        "/prompts/versioned/versions", json=_version_payload(temperature=0.5)
    )
    assert r1.status_code == 201
    assert r1.json()["version"] == 1
    assert r2.json()["version"] == 2

    r = await client.get("/prompts/versioned/versions")
    assert [v["version"] for v in r.json()] == [1, 2]


async def test_get_version_latest_and_pinned(client: AsyncClient) -> None:
    await client.post("/prompts", json={"slug": "lookup"})
    await client.post("/prompts/lookup/versions", json=_version_payload())
    await client.post(
        "/prompts/lookup/versions", json=_version_payload(temperature=0.7)
    )

    latest = await client.get("/prompts/lookup/versions/latest")
    assert latest.status_code == 200
    assert latest.json()["version"] == 2
    assert latest.json()["temperature"] == 0.7

    pinned = await client.get("/prompts/lookup/versions/1")
    assert pinned.status_code == 200
    assert pinned.json()["version"] == 1
    assert pinned.json()["temperature"] == 0.0


async def test_get_version_missing_404(client: AsyncClient) -> None:
    await client.post("/prompts", json={"slug": "noversions"})
    r = await client.get("/prompts/noversions/versions/1")
    assert r.status_code == 404


async def test_version_round_trips_complex_fields(client: AsyncClient) -> None:
    await client.post("/prompts", json={"slug": "complex"})
    payload = _version_payload(
        stop_sequences=["</answer>"],
        tool_selection=["search_lv_items"],
        output_schema_ref="AssertionExtractionResult",
        top_p=0.9,
    )
    r = await client.post("/prompts/complex/versions", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["stop_sequences"] == ["</answer>"]
    assert body["tool_selection"] == ["search_lv_items"]
    assert body["output_schema_ref"] == "AssertionExtractionResult"
    assert body["top_p"] == 0.9
