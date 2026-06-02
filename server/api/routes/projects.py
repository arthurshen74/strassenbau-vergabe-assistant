from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncConnection

from api.deps import get_connection, get_search, get_storage, get_uow
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import StorageClient
from shared.db.unit_of_work import UnitOfWork
from shared.models.document_schema import DocumentRead
from shared.models.enums import DocumentType
from shared.models.project_schema import ProjectCreate, ProjectRead
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.projects import ProjectRepository
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
