from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from api.deps import get_engine
from api.main import app


async def test_health_returns_ok(engine: AsyncEngine) -> None:
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_db_returns_ok(engine: AsyncEngine) -> None:
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/db")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
