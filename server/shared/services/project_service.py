"""Business logic for projects and their documents.

Reads translate domain models to API DTOs. `ingest_documents` is the upload path: each uploaded
file (or, for a `.zip`, each flattened entry) is stored to object storage under
`raw/{document_uuid}`, recorded as a `Document`, and enqueued as a queued `IngestJob` for the
worker to process later. Storage writes are offloaded to a thread because the StorageClient is
synchronous boto3.
"""

from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

import pdfplumber

from shared.clients.storage.client import StorageClient, raw_object_key
from shared.models.document import NewDocument
from shared.models.document_schema import DocumentRead
from shared.models.enums import DocumentType
from shared.models.ingest_job import NewIngestJob
from shared.models.project_schema import ProjectCreate, ProjectRead
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.projects import ProjectRepository

logger = logging.getLogger(__name__)

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_DEFAULT = "application/octet-stream"
ZIP_SUFFIX = ".zip"


class LVDocumentExistsError(Exception):
    """A project already has its single LV document; another was attempted."""


@dataclass(frozen=True)
class UploadInput:
    """One file to ingest: its name, content type, and raw bytes."""

    file_name: str
    content_type: str
    data: bytes


class ProjectService:
    def __init__(
        self,
        projects: ProjectRepository,
        documents: DocumentRepository,
        ingest_jobs: IngestJobRepository,
        storage: StorageClient | None = None,
    ) -> None:
        self.projects = projects
        self.documents = documents
        self.ingest_jobs = ingest_jobs
        self.storage = storage

    async def list(self) -> list[ProjectRead]:
        return [ProjectRead.model_validate(p) for p in await self.projects.list()]

    async def get(self, project_uuid: UUID) -> ProjectRead | None:
        found = await self.projects.get(project_uuid)
        return ProjectRead.model_validate(found) if found else None

    async def create(self, payload: ProjectCreate) -> ProjectRead:
        from shared.models.project import NewProject

        created = await self.projects.add(NewProject(**payload.model_dump()))
        return ProjectRead.model_validate(created)

    async def list_documents(self, project_uuid: UUID) -> list[DocumentRead]:
        docs = await self.documents.list_by_project(project_uuid)
        return [DocumentRead.model_validate(d) for d in docs]

    async def ingest_documents(
        self,
        project_uuid: UUID,
        uploads: list[UploadInput],
        document_type: DocumentType,
    ) -> list[DocumentRead]:
        """Store each file (zip entries flattened) and create Document + queued IngestJob rows."""
        assert self.storage is not None, "ingest requires a storage client"
        created: list[DocumentRead] = []
        for upload in uploads:
            if upload.file_name.lower().endswith(ZIP_SUFFIX):
                # ZIP entries are always prose; the single LV is uploaded on its own.
                for entry in _expand_zip(upload.data):
                    created.append(
                        await self._ingest_one(project_uuid, entry, DocumentType.PROSE_DOCUMENT)
                    )
            else:
                created.append(await self._ingest_one(project_uuid, upload, document_type))
        return created

    async def _ingest_one(
        self, project_uuid: UUID, upload: UploadInput, document_type: DocumentType
    ) -> DocumentRead:
        if document_type == DocumentType.LV_DOCUMENT:
            if await self.documents.get_lv_document(project_uuid) is not None:
                raise LVDocumentExistsError(
                    f"project {project_uuid} already has an LV document"
                )
        doc = await self.documents.add(
            NewDocument(
                project_uuid=project_uuid,
                document_type=document_type,
                file_name=upload.file_name,
                number_of_pages=_count_pdf_pages(upload),
            )
        )
        assert self.storage is not None
        await asyncio.to_thread(
            self.storage.put_object,
            raw_object_key(doc.document_uuid),
            upload.data,
            upload.content_type,
        )
        await self.ingest_jobs.add(NewIngestJob(document_uuid=doc.document_uuid))
        return DocumentRead.model_validate(doc)


def _expand_zip(data: bytes) -> list[UploadInput]:
    """Flatten a zip to its files: directory structure and macOS junk are dropped."""
    out: list[UploadInput] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = PurePosixPath(info.filename).name
            if not name or name.startswith(".") or "__MACOSX" in info.filename:
                continue
            content_type = mimetypes.guess_type(name)[0] or CONTENT_TYPE_DEFAULT
            out.append(UploadInput(name, content_type, zf.read(info)))
    return out


def _count_pdf_pages(upload: UploadInput) -> int:
    """Page count for PDFs (0 for anything else or on a parse error)."""
    if upload.content_type != CONTENT_TYPE_PDF and not upload.file_name.lower().endswith(".pdf"):
        return 0
    try:
        with pdfplumber.open(io.BytesIO(upload.data)) as pdf:
            return len(pdf.pages)
    except Exception:
        logger.warning("could not count pages for %s", upload.file_name)
        return 0
