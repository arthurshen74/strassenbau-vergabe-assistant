"""Business logic for projects and their documents.

Reads translate domain models to API DTOs. `ingest_documents` is the upload path: each
uploaded file (or, for a `.zip`, each entry of the recursively expanded archive) is
stored to object storage under `raw/{document_uuid}`, recorded as a `Document`, and
enqueued as a queued `IngestJob` for the worker to process later. `create_from_zip` is
the ZIP-first path: it creates a project named after the ZIP, ingests every PDF and
GAEB file inside it the same way, and enqueues the project's Projektinfo job. Storage
writes are offloaded to a thread because the StorageClient is synchronous boto3. The
document type is decided here, server-side: a GAEB file (D83/X83) is an LV document by
definition and is added next to any LV documents the project already has; a PDF that is
a fillable form (decided from its bytes) is a form document whose role comes from its
filename, and a Bieter form is enqueued as skipped; everything else -- including the LV
print-layout PDF -- is prose.

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
from shared.config import settings
from shared.models.document import NewDocument
from shared.models.document_schema import DocumentRead
from shared.models.enums import DocumentType, FormRole, IngestStatus
from shared.models.ingest_job import IngestJob, NewIngestJob
from shared.models.lv_item import LVItem
from shared.models.lv_text import LVText
from shared.models.project import NewProject
from shared.models.project_info_job import NewProjectInfoJob
from shared.models.project_schema import (
    ProjectCreate,
    ProjectFromZipResult,
    ProjectRead,
    ProjectUpdate,
)
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.lv_texts import LVTextRepository
from shared.repositories.project_info_jobs import ProjectInfoJobRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.thumbnails import ThumbnailRepository
from shared.services.ingestion.forms.detect import detect_form_kind
from shared.services.ingestion.forms.role import classify_form_role
from shared.services.ingestion.gaeb import (
    GAEB_D83_SUFFIX,
    GAEB_X83_SUFFIX,
    is_gaeb_lv_file,
)

logger = logging.getLogger(__name__)

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_DEFAULT = "application/octet-stream"
ZIP_SUFFIX = ".zip"
PDF_SUFFIX = ".pdf"
INGESTIBLE_SUFFIXES = frozenset({PDF_SUFFIX, GAEB_D83_SUFFIX, GAEB_X83_SUFFIX})
DEFAULT_PROJECT_NAME = "Projekt"

# Caps on one recursive ZIP expansion; raise them here for larger tenders.
ZIP_MAX_DEPTH = 5
ZIP_MAX_ENTRIES = 1000
ZIP_MAX_TOTAL_BYTES = 2 * 1024**3

MACOS_JUNK_DIR = "__MACOSX"
COLLISION_SEPARATOR = "__"


@dataclass(frozen=True)
class UploadInput:
    """One file to ingest: its name, content type, and raw bytes."""

    file_name: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class ZipExpansion:
    """The ingestible files of a ZIP and the entry paths that were left out."""

    uploads: list[UploadInput]
    skipped: list[str]


class ZipTooLargeError(Exception):
    """A ZIP expansion exceeded one of the ZIP_MAX_* caps."""


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
        lv_texts: LVTextRepository | None = None,
        project_info_jobs: ProjectInfoJobRepository | None = None,
    ) -> None:
        self.projects = projects
        self.documents = documents
        self.ingest_jobs = ingest_jobs
        self.storage = storage
        self.thumbnails = thumbnails
        self.lv_items = lv_items
        self.search = search
        self.lv_texts = lv_texts
        self.project_info_jobs = project_info_jobs

    async def list(self) -> list[ProjectRead]:
        return [ProjectRead.model_validate(p) for p in await self.projects.list()]

    async def get(self, project_uuid: UUID) -> ProjectRead | None:
        found = await self.projects.get(project_uuid)
        return ProjectRead.model_validate(found) if found else None

    async def create(self, payload: ProjectCreate) -> ProjectRead:
        created = await self.projects.add(NewProject(**payload.model_dump()))
        return ProjectRead.model_validate(created)

    async def update(
        self, project_uuid: UUID, payload: ProjectUpdate
    ) -> ProjectRead | None:
        """Apply the fields present in the payload; absent fields are left untouched.
        Returns None if the project does not exist."""
        updated = await self.projects.update(
            project_uuid, **payload.model_dump(exclude_unset=True)
        )
        return ProjectRead.model_validate(updated) if updated else None

    async def list_documents(self, project_uuid: UUID) -> list[DocumentRead]:
        docs = await self.documents.list_by_project(project_uuid)
        return [DocumentRead.model_validate(d) for d in docs]

    async def list_lv_items(self, project_uuid: UUID) -> list[LVItem]:
        assert self.lv_items is not None
        return await self.lv_items.list_by_project(project_uuid)

    async def list_lv_texts(self, project_uuid: UUID) -> list[LVText]:
        assert self.lv_texts is not None
        return await self.lv_texts.list_by_project(project_uuid)

    async def list_document_lv_items(
        self, project_uuid: UUID, document_uuid: UUID
    ) -> list[LVItem] | None:
        """One document's LV items; None if the document is not in the project."""
        assert self.lv_items is not None
        if not await self._in_project(project_uuid, document_uuid):
            return None
        return await self.lv_items.list_by_document(document_uuid)

    async def list_document_lv_texts(
        self, project_uuid: UUID, document_uuid: UUID
    ) -> list[LVText] | None:
        """One document's LV texts; None if the document is not in the project."""
        assert self.lv_texts is not None
        if not await self._in_project(project_uuid, document_uuid):
            return None
        return await self.lv_texts.list_by_document(document_uuid)

    async def _in_project(self, project_uuid: UUID, document_uuid: UUID) -> bool:
        doc = await self.documents.get(document_uuid)
        return doc is not None and doc.project_uuid == project_uuid

    async def delete_document(self, project_uuid: UUID, document_uuid: UUID) -> bool:
        """Remove a document and everything derived from it. The DB delete cascades to
        thumbnails, source_lines, lv_items, lv_texts, and ingest_jobs; Elasticsearch
        chunks and
        object-storage blobs are cleaned up explicitly. Returns False if the document
        does not exist in the project.

        External cleanup (ES, storage) is best-effort: a failure is logged and the DB
        delete still proceeds, so the outcome is an orphaned blob/chunk to reconcile
        rather than a DB row pointing at data that is half-gone."""
        assert self.storage is not None
        assert self.thumbnails is not None
        assert self.lv_items is not None
        assert self.lv_texts is not None
        assert self.search is not None

        doc = await self.documents.get(document_uuid)
        if doc is None or doc.project_uuid != project_uuid:
            return False

        # Read derived keys before the cascade removes the rows that name them.
        thumbnails = await self.thumbnails.list_by_document(document_uuid)
        lv_source_uuids = await self.lv_items.list_uuids_by_document(
            document_uuid
        ) + await self.lv_texts.list_uuids_by_document(document_uuid)

        try:
            await self.search.archive_and_delete_document(
                project_uuid, document_uuid, lv_source_uuids
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
        """Store each file (zips expanded recursively) and create Document + queued
        IngestJob rows."""
        assert self.storage is not None, "ingest requires a storage client"
        created: list[DocumentRead] = []
        for upload in uploads:
            if upload.file_name.lower().endswith(ZIP_SUFFIX):
                for entry in expand_zip(upload.data).uploads:
                    created.append(await self._ingest_one(project_uuid, entry))
            else:
                created.append(await self._ingest_one(project_uuid, upload))
        return created

    async def create_from_zip(
        self, file_name: str, data: bytes
    ) -> ProjectFromZipResult:
        """Create a project named after the ZIP and ingest every PDF and GAEB file in
        it. The ZIP is expanded before the project is inserted so an oversized or
        corrupt archive creates nothing."""
        assert self.storage is not None, "ingest requires a storage client"
        expansion = expand_zip(data, allowed_suffixes=INGESTIBLE_SUFFIXES)
        project = await self.projects.add(
            NewProject(project_name=_project_name_from_zip(file_name))
        )
        documents = [
            await self._ingest_one(project.project_uuid, upload)
            for upload in expansion.uploads
        ]
        await self._after_zip_ingest(project.project_uuid)
        return ProjectFromZipResult(
            project=ProjectRead.model_validate(project),
            documents=documents,
            skipped=expansion.skipped,
        )

    async def _after_zip_ingest(self, project_uuid: UUID) -> None:
        """Enqueue the project's Projektinfo job; the worker claims it once the
        documents just enqueued have been ingested. `overwrite` because the only value
        already set is the placeholder name taken from the ZIP."""
        assert self.project_info_jobs is not None
        await self.project_info_jobs.add(
            NewProjectInfoJob(
                project_uuid=project_uuid,
                language=settings.project_info_language,
                overwrite=True,
            )
        )

    async def _ingest_one(
        self, project_uuid: UUID, upload: UploadInput
    ) -> DocumentRead:
        document_type, form_role, form_id = classify_document(
            upload.file_name, upload.data
        )
        doc = await self.documents.add(
            NewDocument(
                project_uuid=project_uuid,
                document_type=document_type,
                file_name=upload.file_name,
                number_of_pages=_count_pdf_pages(upload),
                form_role=form_role,
                form_id=form_id,
            )
        )
        assert self.storage is not None
        await asyncio.to_thread(
            self.storage.put_object,
            raw_object_key(doc.document_uuid),
            upload.data,
            upload.content_type,
        )
        status = (
            IngestStatus.SKIPPED
            if form_role is FormRole.BIETER
            else IngestStatus.QUEUED
        )
        await self.ingest_jobs.add(
            NewIngestJob(document_uuid=doc.document_uuid, status=status)
        )
        return DocumentRead.model_validate(doc)


def classify_document(
    file_name: str, data: bytes
) -> tuple[DocumentType, FormRole | None, str | None]:
    """(document type, form role, form id) of an upload. A GAEB D83/X83 file is an LV
    document by definition; a PDF that is a fillable form is a form document with its
    role and Formblatt id from the filename; everything else -- including the LV
    print-layout PDF -- is prose."""
    if is_gaeb_lv_file(file_name):
        return DocumentType.LV_DOCUMENT, None, None
    if file_name.lower().endswith(PDF_SUFFIX) and detect_form_kind(data) is not None:
        role, form_id = classify_form_role(file_name)
        return DocumentType.FORM_DOCUMENT, role, form_id
    return DocumentType.PROSE_DOCUMENT, None, None


def _project_name_from_zip(file_name: str) -> str:
    """The ZIP's file name without directory and `.zip` suffix (any case)."""
    name = PurePosixPath(file_name).name
    if name.lower().endswith(ZIP_SUFFIX):
        name = name[: -len(ZIP_SUFFIX)]
    return name.strip() or DEFAULT_PROJECT_NAME


def expand_zip(
    data: bytes, *, allowed_suffixes: frozenset[str] | None = None
) -> ZipExpansion:
    """Flatten a zip, and every zip nested in it, to its files.

    Directory structure, dotfiles and macOS junk are dropped silently. With
    `allowed_suffixes`, files with any other suffix go to `skipped`; a corrupt nested
    zip always does. Skipped entries are named by their path, nested levels joined with
    `/`. Raises ZipTooLargeError past a ZIP_MAX_* cap and zipfile.BadZipFile if `data`
    itself is not a zip."""
    walk = _ZipWalk(allowed_suffixes)
    walk.expand(data, prefix="", outer_stem="", depth=1)
    return ZipExpansion(uploads=_dedupe_names(walk.found), skipped=walk.skipped)


@dataclass(frozen=True)
class _ZipEntry:
    parent: str
    upload: UploadInput


class _ZipWalk:
    """Depth-first expansion state shared across nesting levels: caps and results."""

    def __init__(self, allowed_suffixes: frozenset[str] | None) -> None:
        self.allowed_suffixes = allowed_suffixes
        self.entries = 0
        self.total_bytes = 0
        self.found: list[_ZipEntry] = []
        self.skipped: list[str] = []

    def expand(self, data: bytes, *, prefix: str, outer_stem: str, depth: int) -> None:
        if depth > ZIP_MAX_DEPTH:
            raise ZipTooLargeError(f"zip nesting exceeds ZIP_MAX_DEPTH={ZIP_MAX_DEPTH}")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                self._count(info)
                # Zips made on Windows use backslash separators.
                path = PurePosixPath(info.filename.replace("\\", "/"))
                name = path.name
                if not name or name.startswith(".") or MACOS_JUNK_DIR in path.parts:
                    continue
                logical_path = f"{prefix}{path}"
                suffix = path.suffix.lower()
                if suffix == ZIP_SUFFIX:
                    self._expand_nested(zf, info, logical_path, path.stem, depth)
                    continue
                if (
                    self.allowed_suffixes is not None
                    and suffix not in self.allowed_suffixes
                ):
                    self.skipped.append(logical_path)
                    continue
                content_type = mimetypes.guess_type(name)[0] or CONTENT_TYPE_DEFAULT
                upload = UploadInput(name, content_type, zf.read(info))
                self.found.append(_ZipEntry(path.parent.name or outer_stem, upload))

    def _expand_nested(
        self,
        zf: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        logical_path: str,
        stem: str,
        depth: int,
    ) -> None:
        try:
            self.expand(
                zf.read(info),
                prefix=f"{logical_path}/",
                outer_stem=stem,
                depth=depth + 1,
            )
        except zipfile.BadZipFile:
            logger.warning("skipping corrupt nested zip %s", logical_path)
            self.skipped.append(logical_path)

    def _count(self, info: zipfile.ZipInfo) -> None:
        """Charge one entry against the caps before it is read."""
        self.entries += 1
        if self.entries > ZIP_MAX_ENTRIES:
            raise ZipTooLargeError(
                f"zip has more than ZIP_MAX_ENTRIES={ZIP_MAX_ENTRIES} files"
            )
        self.total_bytes += info.file_size
        if self.total_bytes > ZIP_MAX_TOTAL_BYTES:
            raise ZipTooLargeError(
                f"zip unpacks to more than ZIP_MAX_TOTAL_BYTES={ZIP_MAX_TOTAL_BYTES} "
                "bytes"
            )


def _dedupe_names(entries: list[_ZipEntry]) -> list[UploadInput]:
    """Keep each basename once; a repeat is prefixed with its parent directory name
    (`Los2__LV.pdf`), then numbered before the suffix (`Los2__LV-2.pdf`) if it still
    collides, so the suffix that classifies the file is kept."""
    used: set[str] = set()
    out: list[UploadInput] = []
    for entry in entries:
        name = entry.upload.file_name
        if name in used and entry.parent:
            name = f"{entry.parent}{COLLISION_SEPARATOR}{name}"
        if name in used:
            path = PurePosixPath(name)
            n = 2
            while f"{path.stem}-{n}{path.suffix}" in used:
                n += 1
            name = f"{path.stem}-{n}{path.suffix}"
        used.add(name)
        out.append(UploadInput(name, entry.upload.content_type, entry.upload.data))
    return out


def _count_pdf_pages(upload: UploadInput) -> int:
    """Page count for PDFs (0 for anything else or on a parse error)."""
    if (
        upload.content_type != CONTENT_TYPE_PDF
        and not upload.file_name.lower().endswith(PDF_SUFFIX)
    ):
        return 0
    try:
        with pdfplumber.open(io.BytesIO(upload.data)) as pdf:
            return len(pdf.pages)
    except Exception:
        logger.warning("could not count pages for %s", upload.file_name)
        return 0
