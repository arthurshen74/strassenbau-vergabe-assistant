from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


def get_engine(request: Request) -> AsyncEngine:
    return request.app.state.engine


async def get_connection(
    engine: AsyncEngine = Depends(get_engine),
) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        yield conn


async def get_uow(
    engine: AsyncEngine = Depends(get_engine),
) -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as conn:
        yield conn
