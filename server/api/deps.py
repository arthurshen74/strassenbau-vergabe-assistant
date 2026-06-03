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

from shared.clients.embeddings import EmbeddingsClient
from shared.clients.factory import TelemetrySinks
from shared.clients.llm.client import LLMClient
from shared.clients.rerank import RerankClient
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import StorageClient
from shared.db.unit_of_work import UnitOfWork
from shared.services.dispatcher import Dispatcher
from shared.services.project_chat import ProjectChatService
from shared.services.retrieval import RetrievalService


def get_engine(request: Request) -> AsyncEngine:
    return request.app.state.engine


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_storage(request: Request) -> StorageClient:
    return request.app.state.storage


def get_search(request: Request) -> SearchClient:
    return request.app.state.search


def get_embeddings(request: Request) -> EmbeddingsClient:
    return request.app.state.embeddings


def get_reranker(request: Request) -> RerankClient:
    return request.app.state.reranker


def get_telemetry_sinks(request: Request) -> TelemetrySinks:
    return request.app.state.telemetry_sinks


def get_dispatcher(
    engine: AsyncEngine = Depends(get_engine),
    llm: LLMClient = Depends(get_llm_client),
) -> Dispatcher:
    return Dispatcher(llm, engine)


def get_project_chat_service(
    engine: AsyncEngine = Depends(get_engine),
    llm: LLMClient = Depends(get_llm_client),
    embeddings: EmbeddingsClient = Depends(get_embeddings),
    search: SearchClient = Depends(get_search),
    reranker: RerankClient = Depends(get_reranker),
    sinks: TelemetrySinks = Depends(get_telemetry_sinks),
) -> ProjectChatService:
    retrieval = RetrievalService(
        engine=engine, llm=llm, embeddings=embeddings, search=search, reranker=reranker
    )
    return ProjectChatService(llm=llm, engine=engine, retrieval=retrieval, sinks=sinks)


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
