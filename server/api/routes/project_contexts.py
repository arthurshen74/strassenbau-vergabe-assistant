"""Project context endpoints: the flat current view, governance history, override, and resolve.

Reads project the current version of every context global; PUT appends user (HITL) versions;
POST /resolve runs the RAG + synthesis resolution for any global not yet present. Writes go
through the request UnitOfWork; the resolve path additionally builds a RetrievalService and
loads the dedicated PROJECT_CONTEXT_RESOLVE prompt (skipped in mock mode).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from api.deps import (
    Principal,
    get_connection,
    get_current_user,
    get_embeddings,
    get_engine,
    get_llm_client,
    get_reranker,
    get_search,
    get_uow,
)
from shared.clients.embeddings import EmbeddingsClient
from shared.clients.llm.client import LLMClient
from shared.clients.rerank import RerankClient
from shared.clients.search.client import SearchClient
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.project_context_schema import (
    ProjectContextHistory,
    ProjectContextRead,
    ProjectContextUpdate,
)
from shared.repositories.projects import ProjectRepository
from shared.services.project_context import ProjectContextService
from shared.services.project_context.prompts import load_resolve_prompt
from shared.services.project_context.service import DEFAULT_USER
from shared.services.retrieval import RetrievalService

router = APIRouter(prefix="/projects", tags=["project-context"])


async def _ensure_project(conn: AsyncConnection, project_uuid: UUID) -> None:
    if await ProjectRepository(conn).get(project_uuid) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")


@router.get("/{project_uuid}/context", response_model=ProjectContextRead)
async def get_context(
    project_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> ProjectContextRead:
    await _ensure_project(conn, project_uuid)
    return await ProjectContextService(conn).current_read(project_uuid)


@router.get(
    "/{project_uuid}/context/history", response_model=list[ProjectContextHistory]
)
async def get_context_history(
    project_uuid: UUID,
    conn: AsyncConnection = Depends(get_connection),
) -> list[ProjectContextHistory]:
    """Per-variable version history (governance view)."""
    await _ensure_project(conn, project_uuid)
    return await ProjectContextService(conn).history(project_uuid)


@router.put("/{project_uuid}/context", response_model=ProjectContextRead)
async def update_context(
    project_uuid: UUID,
    payload: ProjectContextUpdate,
    uow: UnitOfWork = Depends(get_uow),
    _principal: Principal = Depends(get_current_user),
) -> ProjectContextRead:
    """Override one or more globals; each changed field appends a new HITL version."""
    await _ensure_project(uow.conn, project_uuid)
    return await ProjectContextService(uow.conn).save(
        project_uuid, payload, benutzer=DEFAULT_USER
    )


@router.post("/{project_uuid}/context/resolve", response_model=ProjectContextRead)
async def resolve_context(
    project_uuid: UUID,
    uow: UnitOfWork = Depends(get_uow),
    engine: AsyncEngine = Depends(get_engine),
    llm: LLMClient = Depends(get_llm_client),
    embeddings: EmbeddingsClient = Depends(get_embeddings),
    search: SearchClient = Depends(get_search),
    reranker: RerankClient = Depends(get_reranker),
    _principal: Principal = Depends(get_current_user),
) -> ProjectContextRead:
    """Resolve every global not yet present (RAG + synthesis + geocode/route) and persist it."""
    await _ensure_project(uow.conn, project_uuid)
    retrieval = RetrievalService(
        engine=engine, llm=llm, embeddings=embeddings, search=search, reranker=reranker
    )
    prompt = None if settings.calculator_mock else await load_resolve_prompt(uow.conn)
    return await ProjectContextService(uow.conn).resolve(
        project_uuid, retrieval=retrieval, llm=llm, prompt=prompt
    )
