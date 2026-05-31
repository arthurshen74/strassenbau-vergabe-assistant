from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

import shared.db.tables  # noqa: F401  -- registers all tables on the shared metadata
from shared.config import settings
from shared.db.metadata import metadata


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(settings.test_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Per-test connection wrapped in a transaction that always rolls back."""
    async with engine.connect() as connection:
        trans = await connection.begin()
        try:
            yield connection
        finally:
            await trans.rollback()
