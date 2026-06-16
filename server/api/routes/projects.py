from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Literal
from uuid import UUID

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from api.deps import (
    Principal,
    get_connection,
    get_current_user,
    get_embeddings,
    get_engine,
    get_search,
    get_storage,
    get_uow,
)
from api.sse import SSE_HEARTBEAT, SSE_MEDIA_TYPE, format_sse
from shared.clients.embeddings import EmbeddingsClient
from shared.clients.maps.client import MAP_CONTENT_TYPE
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import StorageClient, map_object_key
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.document_schema import (
    ActivityListRead,
    ChunkListRead,
    DocumentDetailRead,
    DocumentRead,
)
from shared.models.enums import SourceDocType
from shared.models.ingest_schema import IngestJobRead
from shared.models.lv_item import LVItem
from shared.models.project_schema import ProjectCreate, ProjectRead
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.thumbnails import ThumbnailRepository
from shared.services.document_detail import DocumentDetailService
from shared.services.ingestion.status_stream import HEARTBEAT, stream_project_status
from shared.services.lv_item_search import LVItemSearchService
from shared.services.project_service import ProjectService, UploadInput

router = APIRouter(prefix="/projects", tags=["projects"])

# Page thumbnails are immutable once ingested (re-ingestion replaces the row), so cache hard.
THUMBNAIL_CACHE_CONTROL = "public, max-age=86400, immutable"

# Rendered maps are addressed by a hash of their request params, so they're immutable too.
MAP_CACHE_CONTROL = "public, max-age=86400, immutable"


def get_project_service(
    conn: AsyncConnection = Depends(get_connection),
) -> ProjectService:
    return ProjectService(
        ProjectRepository(conn),
        DocumentRepository(conn),
        IngestJobRepository(conn),
        lv_items=LVItemRepository(conn),
    )


def get_writable_project_service(
    uow: UnitOfWork = Depends(get_uow),
    storage: StorageClient = Depends(get_storage),
) -> ProjectService:
    return ProjectService(uow.projects, uow.documents, uow.ingest_jobs, storage=storage)


def get_deletable_project_service(
    uow: UnitOfWork = Depends(get_uow),
    storage: StorageClient = Depends(get_storage),
    search: SearchClient = Depends(get_search),
) -> ProjectService:
    return ProjectService(
        uow.projects,
        uow.documents,
        uow.ingest_jobs,
        storage=storage,
        thumbnails=uow.thumbnails,
        lv_items=uow.lv_items,
        search=search,
    )


def get_document_detail_service(
    engine: AsyncEngine = Depends(get_engine),
    search: SearchClient = Depends(get_search),
) -> DocumentDetailService:
    return DocumentDetailService(engine, search)


def get_lv_item_search_service(
    engine: AsyncEngine = Depends(get_engine),
    embeddings: EmbeddingsClient = Depends(get_embeddings),
    search: SearchClient = Depends(get_search),
) -> LVItemSearchService:
    return LVItemSearchService(engine=engine, embeddings=embeddings, search=search)


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectRead]:
    return await service.list()


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    service: ProjectService = Depends(get_writable_project_service),
) -> ProjectRead:
    return await service.create(payload)


@router.get("/{project_uuid}", response_model=ProjectRead)
async def get_project(
    project_uuid: UUID,
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    found = await service.get(project_uuid)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return found


@router.get("/{project_uuid}/documents", response_model=list[DocumentRead])
async def list_documents(
    project_uuid: UUID,
    service: ProjectService = Depends(get_project_service),
) -> list[DocumentRead]:
    return await service.list_documents(project_uuid)


@router.get("/{project_uuid}/lv-items", response_model=list[LVItem])
async def list_lv_items(
    project_uuid: UUID,
    service: ProjectService = Depends(get_project_service),
) -> list[LVItem]:
    """All LV positions for the project's LV document, ordered by oz."""
    return await service.list_lv_items(project_uuid)


@router.get("/{project_uuid}/lv-items/search", response_model=list[LVItem])
async def search_lv_items(
    project_uuid: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    service: LVItemSearchService = Depends(get_lv_item_search_service),
) -> list[LVItem]:
    """LV positions matching q in relevance order: hybrid BM25 + semantic search over the
    project's LV_ITEM chunks, with exact oz/stl_nr position matches surfaced first."""
    return await service.search(project_uuid, q, limit=limit)


@router.get("/{project_uuid}/ingest/stream")
async def ingest_status_stream(
    project_uuid: UUID,
    principal: Principal = Depends(get_current_user),
    engine: AsyncEngine = Depends(get_engine),
) -> StreamingResponse:
    """Stream per-document ingest status for the project as SSE IngestEvents.

    The existence check uses a short-lived connection; the stream itself opens a fresh connection
    per poll tick rather than holding one for its whole (long) lifetime."""
    async with engine.connect() as conn:
        if await ProjectRepository(conn).get(project_uuid) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

    async def event_stream() -> AsyncIterator[str]:
        async for event in stream_project_status(
            engine, project_uuid, poll_interval=settings.ingest_status_poll_interval_seconds
        ):
            yield SSE_HEARTBEAT if event.get(HEARTBEAT) else format_sse(event)

    return StreamingResponse(event_stream(), media_type=SSE_MEDIA_TYPE)


@router.post(
    "/{project_uuid}/documents",
    response_model=list[DocumentRead],
    status_code=status.HTTP_201_CREATED,
)
async def upload_documents(
    project_uuid: UUID,
    files: list[UploadFile] = File(...),
    # Deletable service: a GAEB upload replaces the project's existing LV document,
    # which needs the thumbnail/LV/search dependencies of the delete path.
    service: ProjectService = Depends(get_deletable_project_service),
) -> list[DocumentRead]:
    """Upload project documents. The document type comes from each filename: GAEB D83/X83
    files become the LV document (replacing an existing one); everything else is prose."""
    if await service.get(project_uuid) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    uploads = [
        UploadInput(
            file_name=f.filename or "upload",
            content_type=f.content_type or "application/octet-stream",
            data=await f.read(),
        )
        for f in files
    ]
    return await service.ingest_documents(project_uuid, uploads)


@router.post(
    "/{project_uuid}/documents/{document_uuid}/ingest",
    response_model=IngestJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_document(
    project_uuid: UUID,
    document_uuid: UUID,
    service: ProjectService = Depends(get_writable_project_service),
) -> IngestJobRead:
    """Queue a (re-)ingest of an existing document; the worker picks it up and progress streams
    over the project's ingest status SSE."""
    job = await service.enqueue_ingest(project_uuid, document_uuid)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return IngestJobRead.model_validate(job)


@router.delete(
    "/{project_uuid}/documents/{document_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    project_uuid: UUID,
    document_uuid: UUID,
    service: ProjectService = Depends(get_deletable_project_service),
) -> None:
    deleted = await service.delete_document(project_uuid, document_uuid)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="document not found"
        )


@router.get("/{project_uuid}/documents/{document_uuid}/pages/{page_number}/thumbnail")
async def get_page_thumbnail(
    project_uuid: UUID,
    document_uuid: UUID,
    page_number: int,
    conn: AsyncConnection = Depends(get_connection),
    storage: StorageClient = Depends(get_storage),
) -> Response:
    """Serve a document page's thumbnail image, proxied from object storage (MinIO isn't
    reachable from the browser in local dev). Scoped to the project so a thumbnail can't be
    pulled across projects."""
    document = await DocumentRepository(conn).get(document_uuid)
    if document is None or document.project_uuid != project_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    thumbnail = await ThumbnailRepository(conn).get_by_page(document_uuid, page_number)
    if thumbnail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thumbnail not found")
    data = await asyncio.to_thread(storage.get_object, thumbnail.object_key)
    return Response(
        content=data,
        media_type=thumbnail.content_type,
        headers={"Cache-Control": THUMBNAIL_CACHE_CONTROL},
    )


@router.get("/{project_uuid}/maps/{map_id}")
async def get_project_map(
    project_uuid: UUID,
    map_id: str,
    storage: StorageClient = Depends(get_storage),
) -> Response:
    """Serve a rendered static map image, proxied from object storage (MinIO isn't reachable from
    the browser in local dev). The map is keyed under the project, so it can't be pulled across
    projects; a missing key is a 404."""
    key = map_object_key(project_uuid, map_id)
    try:
        data = await asyncio.to_thread(storage.get_object, key)
    except ClientError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="map not found")
    return Response(
        content=data,
        media_type=MAP_CONTENT_TYPE,
        headers={"Cache-Control": MAP_CACHE_CONTROL},
    )


@router.get(
    "/{project_uuid}/documents/{document_uuid}/detail",
    response_model=DocumentDetailRead,
)
async def get_document_detail(
    project_uuid: UUID,
    document_uuid: UUID,
    _principal: Principal = Depends(get_current_user),
    service: DocumentDetailService = Depends(get_document_detail_service),
) -> DocumentDetailRead:
    detail = await service.get_detail(project_uuid, document_uuid)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return detail


@router.get(
    "/{project_uuid}/documents/{document_uuid}/chunks",
    response_model=ChunkListRead,
)
async def list_document_chunks(
    project_uuid: UUID,
    document_uuid: UUID,
    source: Literal["simple", "langchain"] = "simple",
    doc_type: SourceDocType | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 50,
    _principal: Principal = Depends(get_current_user),
    service: DocumentDetailService = Depends(get_document_detail_service),
) -> ChunkListRead:
    """A page of the document's chunks from the chosen index (doc_type/q apply to SimpleChunks)."""
    return await service.list_chunks(
        project_uuid,
        document_uuid,
        source=source,
        source_doc_type=doc_type,
        text=q,
        offset=offset,
        size=limit,
    )


@router.get(
    "/{project_uuid}/documents/{document_uuid}/activity",
    response_model=ActivityListRead,
)
async def list_document_activity(
    project_uuid: UUID,
    document_uuid: UUID,
    offset: int = 0,
    limit: int = 200,
    _principal: Principal = Depends(get_current_user),
    service: DocumentDetailService = Depends(get_document_detail_service),
) -> ActivityListRead:
    """The document's ingestion activity (active then archive), oldest first, paged, with total."""
    return await service.list_activity(document_uuid, offset=offset, limit=limit)
