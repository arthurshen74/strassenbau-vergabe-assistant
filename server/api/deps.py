"""FastAPI dependency-injection wiring for the API layer.

Provides request-scoped database access and the interim auth principal.

Database access comes in two shapes:
- ``get_connection`` yields a read-only ``AsyncConnection`` with no transaction,
  for read paths.
- ``get_uow`` yields a ``UnitOfWork`` wrapped in a transaction that commits on
  success and rolls back on exception, for write paths that compose multiple
  repositories.

Auth is a stub for now: ``Principal`` is the request identity, and
``get_current_user`` always resolves to a hardcoded dev administrator until real
auth (fastapi-users, then OAuth2/JWT) lands.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from shared.clients.llm.client import LLMClient
from shared.clients.storage.client import StorageClient
from shared.db.unit_of_work import UnitOfWork
from shared.services.dispatcher import Dispatcher


def get_engine(request: Request) -> AsyncEngine:
    return request.app.state.engine


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_storage(request: Request) -> StorageClient:
    return request.app.state.storage


def get_dispatcher(
    engine: AsyncEngine = Depends(get_engine),
    llm: LLMClient = Depends(get_llm_client),
) -> Dispatcher:
    return Dispatcher(llm, engine)


async def get_connection(
    engine: AsyncEngine = Depends(get_engine),
) -> AsyncIterator[AsyncConnection]:
    """Read-only connection, no transaction."""
    async with engine.connect() as conn:
        yield conn


async def get_uow(
    engine: AsyncEngine = Depends(get_engine),
) -> AsyncIterator[UnitOfWork]:
    """Transactional unit of work for write operations."""
    async with engine.begin() as conn:
        yield UnitOfWork(conn)


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
