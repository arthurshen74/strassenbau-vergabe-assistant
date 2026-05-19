from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from shared.db.metadata import metadata

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://roadbuilders:roadbuilders@localhost:5432/roadbuilders_test"
)


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    engine = create_async_engine(url)
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
