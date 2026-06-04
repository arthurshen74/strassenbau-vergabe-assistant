from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.unit_of_work import UnitOfWork
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, IngestStatus, SourceDocType
from shared.models.ingest_job import IngestJob, NewIngestJob
from shared.models.project import NewProject
from shared.models.simple_chunk import NewSimpleChunk
from shared.models.source_line import NewSourceLine
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.projects import ProjectRepository
from shared.services.ingestion import ingestion_service as service_module
from worker.main import process_one

# --- fakes (mirror tests/integration/services/test_ingestion_service.py) -------------


class _FakeStorage:
    bucket = "test-bucket"

    def get_object(self, key: str) -> bytes:
        return b"%PDF-fake"

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        pass


class _FakeEmbeddings:
    async def embed(
        self,
        texts: list[str],
        *,
        project_uuid: Any = None,
        ingest_job_uuid: Any = None,
        document_uuid: Any = None,
    ) -> list[list[float]]:
        return [[float(i)] for i in range(len(texts))]


class _RecordingSearch:
    def __init__(self) -> None:
        self.indexed: list[NewSimpleChunk] = []

    async def archive_source(self, source_doc_uuid: UUID, source_doc_type: SourceDocType) -> int:
        return 0

    async def index_chunks(
        self, chunks: list[NewSimpleChunk], *, refresh: bool = False
    ) -> list[UUID]:
        self.indexed.extend(chunks)
        return [uuid4() for _ in chunks]


class _FakePrompts:
    async def run_lv_extraction(self, numbered_document: str, **_: Any) -> Any:
        raise AssertionError("LV extraction must not run for a prose document")


class _FakeLangchain:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def ingest(
        self,
        document_uuid: UUID,
        project_uuid: UUID,
        pdf_bytes: bytes,
        *,
        ingest_job_uuid: UUID | None = None,
    ) -> int:
        self.calls.append((document_uuid, project_uuid))
        return 0


# --- helpers -------------------------------------------------------------


def _factory(conn: AsyncConnection):
    @asynccontextmanager
    async def factory() -> AsyncIterator[UnitOfWork]:
        yield UnitOfWork(conn)

    return factory


async def _queued_job(conn: AsyncConnection) -> IngestJob:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-WORKER",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name="p.pdf",
            number_of_pages=1,
        )
    )
    return await IngestJobRepository(conn).add(NewIngestJob(document_uuid=doc.document_uuid))


def _kwargs(search: _RecordingSearch, langchain: _FakeLangchain) -> dict[str, Any]:
    return {
        "worker_id": "test-worker",
        "storage": _FakeStorage(),
        "search": search,
        "embeddings": _FakeEmbeddings(),
        "prompts": _FakePrompts(),
        "langchain_ingestor": langchain,
    }


# --- tests ---------------------------------------------------------------


async def test_process_one_claims_runs_and_marks_done(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "render_thumbnails", lambda _pdf: [])
    monkeypatch.setattr(
        service_module,
        "extract_source_lines",
        lambda _b, doc: [
            NewSourceLine(document_uuid=doc, line_id=0, page=1, bbox=(0, 0, 1, 1), line_text="prose")
        ],
    )
    job = await _queued_job(conn)
    search = _RecordingSearch()
    langchain = _FakeLangchain()

    ran = await process_one(_factory(conn), **_kwargs(search, langchain))  # type: ignore[arg-type]

    assert ran is True
    refreshed = await IngestJobRepository(conn).get(job.job_uuid)
    assert refreshed is not None and refreshed.status == IngestStatus.DONE
    assert search.indexed  # the document was chunked and indexed
    assert langchain.calls  # the langchain pipeline step ran


async def test_process_one_empty_queue_returns_false(conn: AsyncConnection) -> None:
    ran = await process_one(_factory(conn), **_kwargs(_RecordingSearch(), _FakeLangchain()))  # type: ignore[arg-type]
    assert ran is False


async def test_process_one_marks_failed_on_error(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "render_thumbnails", lambda _pdf: [])

    def _boom(_b: bytes, _doc: UUID) -> list[NewSourceLine]:
        raise RuntimeError("extraction blew up")

    monkeypatch.setattr(service_module, "extract_source_lines", _boom)
    job = await _queued_job(conn)

    ran = await process_one(_factory(conn), **_kwargs(_RecordingSearch(), _FakeLangchain()))  # type: ignore[arg-type]

    # The loop survives a failed job: it returns True (work was attempted) and marks FAILED.
    assert ran is True
    refreshed = await IngestJobRepository(conn).get(job.job_uuid)
    assert refreshed is not None and refreshed.status == IngestStatus.FAILED
