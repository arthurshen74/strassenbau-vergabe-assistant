from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_uow
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.enums import ProjectInfoQuery
from shared.models.rag_query_schema import (
    LANGUAGE_PATTERN,
    RagQueryVersionCreate,
    RagQueryVersionRead,
)
from shared.repositories.rag_queries import RagQueryVersionRepository
from shared.services.rag_query_service import RagQueryService

router = APIRouter(prefix="/rag-queries", tags=["rag-queries"])


def get_rag_query_service(
    conn: AsyncConnection = Depends(get_connection),
) -> RagQueryService:
    return RagQueryService(RagQueryVersionRepository(conn))


def get_writable_rag_query_service(
    uow: UnitOfWork = Depends(get_uow),
) -> RagQueryService:
    return RagQueryService(uow.rag_queries)


# Defaults to the server's project-info language.
LanguageQuery = Query(settings.project_info_language, pattern=LANGUAGE_PATTERN)


@router.get("", response_model=list[RagQueryVersionRead])
async def list_latest(
    language: str = LanguageQuery,
    service: RagQueryService = Depends(get_rag_query_service),
) -> list[RagQueryVersionRead]:
    """Latest version per query key in `language`; keys without one are absent."""
    return await service.list_latest(language)


@router.get("/{query_key}/history", response_model=list[RagQueryVersionRead])
async def history(
    query_key: ProjectInfoQuery,
    language: str = LanguageQuery,
    service: RagQueryService = Depends(get_rag_query_service),
) -> list[RagQueryVersionRead]:
    return await service.history(query_key, language)


@router.post(
    "/{query_key}",
    response_model=RagQueryVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def publish(
    query_key: ProjectInfoQuery,
    payload: RagQueryVersionCreate,
    service: RagQueryService = Depends(get_writable_rag_query_service),
) -> RagQueryVersionRead:
    return await service.publish(query_key, payload)
