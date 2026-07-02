"""Project context endpoints: the flat current view, governance history, override, and resolve.

Reads project the current version of every context global; PUT appends user (HITL) versions;
POST /resolve runs the RAG + synthesis resolution for any global not yet present. Writes go
through the request UnitOfWork; the resolve path additionally builds a RetrievalService and
loads the dedicated PROJECT_CONTEXT_RESOLVE prompt (skipped in mock mode).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
from shared.clients.maps.client import (
    MAP_CONTENT_TYPE,
    StaticMapError,
    fetch_route_map_png,
    fetch_static_map_png,
)
from shared.clients.maps.geo import Koordinate, MapsError, geocode, route_polyline
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


# Baustelle confirmation map: closer than the city-level chat map so the marker is unambiguous.
CONTEXT_MAP_ZOOM = 14


@router.get("/{project_uuid}/context/map")
async def get_context_map(
    project_uuid: UUID,
    lat: str,
    lon: str,
    zoom: int = CONTEXT_MAP_ZOOM,
) -> Response:
    """Static map centered on a geocoded context location (the Baustelle), for visual confirmation
    in the pre-Gate-A project-context review. Coordinate-driven (no project data), so no DB lookup;
    the project_uuid scopes the URL. 502 if the Static Maps key is unset or the request fails."""
    try:
        png = await fetch_static_map_png(f"{lat},{lon}", zoom=zoom)
    except StaticMapError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return Response(content=png, media_type=MAP_CONTENT_TYPE)


@router.get("/{project_uuid}/context/route-map")
async def get_context_route_map(
    project_uuid: UUID,
    origin_lat: str,
    origin_lon: str,
    dest_lat: str,
    dest_lon: str,
) -> Response:
    """Static map (4:3) of the Baustelle -> Deponie road route, for the pre-Gate-A review: fetches
    the road polyline (computeRoutes) then renders it with a green origin + red destination marker.
    Coordinate-driven, so no DB lookup; 502 if routing or the Static Maps key fails."""
    origin: Koordinate = (Decimal(origin_lat), Decimal(origin_lon))
    dest: Koordinate = (Decimal(dest_lat), Decimal(dest_lon))
    try:
        _km, polyline = await route_polyline(origin, dest)
        png = await fetch_route_map_png(
            f"{origin_lat},{origin_lon}", f"{dest_lat},{dest_lon}", polyline)
    except (MapsError, StaticMapError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return Response(content=png, media_type=MAP_CONTENT_TYPE)


@router.get("/{project_uuid}/context/geocode")
async def get_context_geocode(project_uuid: UUID, address: str) -> dict[str, object]:
    """Geocode an address on the fly for the Gate-1 'Ändern' modal (coordinate + confidence), so the
    estimator sees the map for an edited location before confirming. 502 on failure."""
    try:
        geo = await geocode(address)
    except MapsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {
        "breitengrad": str(geo.breitengrad),
        "laengengrad": str(geo.laengengrad),
        "formatiert": geo.formatiert,
        "konfidenz": geo.konfidenz,
    }


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


@router.delete("/{project_uuid}/context", response_model=ProjectContextRead)
async def clear_context(
    project_uuid: UUID,
    uow: UnitOfWork = Depends(get_uow),
    _principal: Principal = Depends(get_current_user),
) -> ProjectContextRead:
    """Delete all persisted context versions for a project so the next resolve re-runs from scratch
    (RAG + geocode). Use this to recover a project whose Baustelle was stored before geocoding
    worked. Returns the now-empty context view."""
    await _ensure_project(uow.conn, project_uuid)
    service = ProjectContextService(uow.conn)
    await service.clear(project_uuid)
    return await service.current_read(project_uuid)


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
