"""The /entity-rules API: CRUD roundtrip, spaCy-validated writes, label discovery.

The entity_rules table is shared across the session, so each test clears it first.
Writes go through the app (its own connection), so data is committed via the engine.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine
from api.main import app
from shared.db.tables.entity_rules import entity_rules


@pytest_asyncio.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    async with engine.begin() as conn:
        await conn.execute(delete(entity_rules))
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def test_create_update_delete_roundtrip(client: AsyncClient) -> None:
    created = await client.post(
        "/entity-rules",
        json={"label": "BAUSTOFF", "pattern": "Asphaltbeton", "pattern_id": "b_asphalt"},
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["label"] == "BAUSTOFF"
    assert rule["enabled"] is True
    uuid = rule["entity_rule_uuid"]

    listed = await client.get("/entity-rules")
    assert listed.status_code == 200
    assert [r["entity_rule_uuid"] for r in listed.json()] == [uuid]

    patched = await client.patch(f"/entity-rules/{uuid}", json={"enabled": False})
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False
    assert patched.json()["label"] == "BAUSTOFF"  # untouched field preserved

    deleted = await client.delete(f"/entity-rules/{uuid}")
    assert deleted.status_code == 204
    assert (await client.get("/entity-rules")).json() == []


async def test_invalid_pattern_rejected_422(client: AsyncClient) -> None:
    response = await client.post(
        "/entity-rules",
        json={"label": "BAUSTOFF", "pattern": [{"NOT_A_REAL_ATTR": "x"}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]  # spaCy's message surfaced
    # Nothing persisted.
    assert (await client.get("/entity-rules")).json() == []


async def test_labels_reflects_distinct_set(client: AsyncClient) -> None:
    for label, pattern in [
        ("BAUSTOFF", "Beton"),
        ("BAUSTOFF", "Asphalt"),
        ("EINHEIT", "cm"),
    ]:
        resp = await client.post(
            "/entity-rules", json={"label": label, "pattern": pattern}
        )
        assert resp.status_code == 201

    labels = await client.get("/entity-rules/labels")
    assert labels.status_code == 200
    assert labels.json() == ["BAUSTOFF", "EINHEIT"]


async def test_patch_missing_rule_404(client: AsyncClient) -> None:
    response = await client.patch(
        "/entity-rules/00000000-0000-0000-0000-000000000000",
        json={"enabled": False},
    )
    assert response.status_code == 404
