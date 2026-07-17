"""Business logic for projects and their documents.

Reads translate domain models to API DTOs. `ingest_documents` is the upload path: each
uploaded file (or, for a `.zip`, each flattened entry) is stored to object storage under
`raw/{document_uuid}`, recorded as a `Document`, and enqueued as a queued `IngestJob`
for the worker to process later. Storage writes are offloaded to a thread because the
StorageClient is synchronous boto3. The document type comes from the filename alone: a
GAEB file (D83/X83) is the LV document by definition and supersedes the project's
existing one (the old document is deleted first, removing its LV items from Postgres and
its chunks from Elasticsearch); everything else -- including the LV print-layout PDF --
is prose.

`delete_document` is the inverse: the DB row delete cascades to the document's
thumbnails, source_lines, lv_items, and ingest_jobs, while the Elasticsearch chunks and
object-storage blobs are removed explicitly. The external cleanup is best-effort so a
transient ES/storage failure cannot strand the user with an undeletable document.
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

from shared.clients.search.client import SearchClient
from shared.clients.storage.client import StorageClient, raw_object_key
from shared.models.document import NewDocument
from shared.models.document_schema import DocumentRead
from shared.models.enums import DocumentType
from shared.models.ingest_job import IngestJob, NewIngestJob
from shared.models.lv_item import LVItem
from shared.models.project_schema import ProjectCreate, ProjectRead
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.thumbnails import ThumbnailRepository
from shared.services.ingestion.gaeb import is_gaeb_lv_file

logger = logging.getLogger(__name__)

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_DEFAULT = "application/octet-stream"
ZIP_SUFFIX = ".zip"


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
        thumbnails: ThumbnailRepository | None = None,
        lv_items: LVItemRepository | None = None,
        search: SearchClient | None = None,
    ) -> None:
        self.projects = projects
        self.documents = documents
        self.ingest_jobs = ingest_jobs
        self.storage = storage
        self.thumbnails = thumbnails
        self.lv_items = lv_items
        self.search = search

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

    async def list_lv_items(self, project_uuid: UUID) -> list[LVItem]:
        assert self.lv_items is not None
        return await self.lv_items.list_by_project(project_uuid)

    async def delete_document(self, project_uuid: UUID, document_uuid: UUID) -> bool:
        """Remove a document and everything derived from it. The DB delete cascades to
        thumbnails, source_lines, lv_items, and ingest_jobs; Elasticsearch chunks and
        object-storage blobs are cleaned up explicitly. Returns False if the document
        does not exist in the project.

        External cleanup (ES, storage) is best-effort: a failure is logged and the DB
        delete still proceeds, so the outcome is an orphaned blob/chunk to reconcile
        rather than a DB row pointing at data that is half-gone."""
        assert self.storage is not None
        assert self.thumbnails is not None
        assert self.lv_items is not None
        assert self.search is not None

        doc = await self.documents.get(document_uuid)
        if doc is None or doc.project_uuid != project_uuid:
            return False

        # Read derived keys before the cascade removes the rows that name them.
        thumbnails = await self.thumbnails.list_by_document(document_uuid)
        lv_item_uuids = await self.lv_items.list_uuids_by_document(document_uuid)

        try:
            await self.search.archive_and_delete_document(
                project_uuid, document_uuid, lv_item_uuids
            )
        except Exception:
            logger.exception(
                "elasticsearch cleanup failed for document %s; chunks left orphaned",
                document_uuid,
            )

        keys = [raw_object_key(document_uuid)] + [t.object_key for t in thumbnails]
        try:
            await asyncio.to_thread(self.storage.delete_objects, keys)
        except Exception:
            logger.exception(
                "object storage cleanup failed for document %s; objects left orphaned",
                document_uuid,
            )

        await self.documents.delete(document_uuid)
        return True

    async def delete_project(self, project_uuid: UUID) -> bool:
        """Remove a project and everything under it. Each document is taken down via
        delete_document (its Elasticsearch chunks and object-storage blobs, plus its own
        DB cascade); the project row delete then cascades to conversations and any
        remaining project-scoped rows. Returns False if the project does not exist.

        Per-document external cleanup is best-effort (see delete_document): a transient
        ES/storage failure is logged and leaves an orphaned blob/chunk rather than
        blocking the delete. Rendered project maps under maps/{project_uuid}/ are not
        tracked in Postgres and are left as regenerable orphans."""
        assert self.storage is not None
        assert self.thumbnails is not None
        assert self.lv_items is not None
        assert self.search is not None

        if await self.projects.get(project_uuid) is None:
            return False

        for doc in await self.documents.list_by_project(project_uuid):
            await self.delete_document(project_uuid, doc.document_uuid)

        await self.projects.delete(project_uuid)
        return True

    async def enqueue_ingest(
        self, project_uuid: UUID, document_uuid: UUID
    ) -> IngestJob | None:
        """Re-ingest an existing document by requeuing its job in place: reset to QUEUED
        with a fresh retry budget so the worker reprocesses the raw PDF already in
        object storage (ingestion is idempotent, archiving/replacing the document's
        prior chunks). Keeps one job per document rather than minting a new row; falls
        back to creating a job if the document has none yet. Returns None if the
        document does not exist in the project."""
        doc = await self.documents.get(document_uuid)
        if doc is None or doc.project_uuid != project_uuid:
            return None
        existing = await self.ingest_jobs.latest_for_document(document_uuid)
        if existing is not None:
            return await self.ingest_jobs.requeue(existing.job_uuid)
        return await self.ingest_jobs.add(NewIngestJob(document_uuid=document_uuid))

    async def ingest_documents(
        self,
        project_uuid: UUID,
        uploads: list[UploadInput],
    ) -> list[DocumentRead]:
        """Store each file (zip entries flattened) and create Document + queued
        IngestJob rows."""
        assert self.storage is not None, "ingest requires a storage client"
        created: list[DocumentRead] = []
        for upload in uploads:
            if upload.file_name.lower().endswith(ZIP_SUFFIX):
                for entry in _expand_zip(upload.data):
                    created.append(
                        await self._ingest_one(
                            project_uuid,
                            entry,
                            _classify_document_type(entry.file_name),
                        )
                    )
            else:
                created.append(
                    await self._ingest_one(
                        project_uuid, upload, _classify_document_type(upload.file_name)
                    )
                )
        return created

    async def _ingest_one(
        self, project_uuid: UUID, upload: UploadInput, document_type: DocumentType
    ) -> DocumentRead:
        if document_type == DocumentType.LV_DOCUMENT:
            existing = await self.documents.get_lv_document(project_uuid)
            if existing is not None:
                # A GAEB upload supersedes the project's LV: drop the previous LV
                # document with all its LV items (Postgres cascade) and chunks
                # (Elasticsearch).
                await self.delete_document(project_uuid, existing.document_uuid)
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


def _classify_document_type(file_name: str) -> DocumentType:
    """Assign the document type from the filename, mirroring classifyDocumentType in
    ui/src/lib/documentType.ts: a GAEB D83/X83 file is the LV document by definition;
    everything else -- including the LV print-layout PDF -- is prose."""
    if is_gaeb_lv_file(file_name):
        return DocumentType.LV_DOCUMENT
    return DocumentType.PROSE_DOCUMENT


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
    if (
        upload.content_type != CONTENT_TYPE_PDF
        and not upload.file_name.lower().endswith(".pdf")
    ):
        return 0
    try:
        with pdfplumber.open(io.BytesIO(upload.data)) as pdf:
            return len(pdf.pages)
    except Exception:
        logger.warning("could not count pages for %s", upload.file_name)
        return 0
