from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict
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


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    roles: list[str]
    project_uuids: list[UUID]


# Interim Sprint 2 stub: real auth (fastapi-users, then OAuth2/JWT) lands later; until
# then every request resolves to a dev administrator. See ARCHITECTURE.md "Authentication".
_DEV_PRINCIPAL = Principal(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    roles=["administrator"],
    project_uuids=[],
)


async def get_current_user() -> Principal:
    return _DEV_PRINCIPAL
