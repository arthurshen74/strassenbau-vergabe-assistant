from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from api.deps import (
    Principal,
    get_connection,
    get_current_user,
    get_engine,
    get_search,
    get_storage,
    get_uow,
)
from api.sse import SSE_HEARTBEAT, SSE_MEDIA_TYPE, format_sse
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import StorageClient
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.document_schema import DocumentRead
from shared.models.enums import DocumentType
from shared.models.ingest_schema import IngestJobRead
from shared.models.project_schema import ProjectCreate, ProjectRead
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.projects import ProjectRepository
from shared.services.ingestion.status_stream import HEARTBEAT, stream_project_status
from shared.services.project_service import (
    LVDocumentExistsError,
    ProjectService,
    UploadInput,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_service(
    conn: AsyncConnection = Depends(get_connection),
) -> ProjectService:
    return ProjectService(
        ProjectRepository(conn), DocumentRepository(conn), IngestJobRepository(conn)
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
    document_type: DocumentType = Form(DocumentType.PROSE_DOCUMENT),
    service: ProjectService = Depends(get_writable_project_service),
) -> list[DocumentRead]:
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
    try:
        return await service.ingest_documents(project_uuid, uploads, document_type)
    except LVDocumentExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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
