from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.clients.storage.client import thumbnail_object_key
from shared.db.unit_of_work import UnitOfWork
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, FormRole, SourceDocType
from shared.models.ingest_job import NewIngestJob
from shared.models.project import NewProject
from shared.models.simple_chunk import NewSimpleChunk
from shared.models.source_line import NewSourceLine
from shared.repositories.documents import DocumentRepository
from shared.repositories.form_fields import FormFieldRepository
from shared.repositories.ingest_job_events import IngestJobEventRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.source_lines import SourceLineRepository
from shared.repositories.thumbnails import ThumbnailRepository
from shared.services.ingestion import IngestionService
from shared.services.ingestion import ingestion_service as service_module
from shared.services.ingestion.thumbnails import RenderedPage
from tests.form_pdfs import FieldSpec, acroform_pdf, hva_111_page, text_field

# --- fakes ---------------------------------------------------------------


class _FakeStorage:
    bucket = "test-bucket"

    def __init__(self, data: bytes = b"%PDF-fake") -> None:
        self.data = data
        self.puts: list[tuple[str, str]] = []

    def get_object(self, key: str) -> bytes:
        return self.data

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.puts.append((key, content_type))


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


class _FakeLangchain:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID, UUID | None]] = []

    async def ingest(
        self,
        document_uuid: UUID,
        project_uuid: UUID,
        pdf_bytes: bytes,
        *,
        ingest_job_uuid: UUID | None = None,
        activity: Any = None,
    ) -> int:
        self.calls.append((document_uuid, project_uuid, ingest_job_uuid))
        return 0


class _RecordingSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.indexed: list[NewSimpleChunk] = []

    async def archive_sources(
        self, source_doc_uuids: list[UUID], source_doc_type: SourceDocType
    ) -> int:
        self.calls.append(("archive", (set(source_doc_uuids), source_doc_type)))
        return 0

    async def index_chunks(self, chunks: list[NewSimpleChunk], *, refresh: bool = False) -> list[UUID]:
        self.calls.append(("index", [c.source_doc_type for c in chunks]))
        self.indexed.extend(chunks)
        return [uuid4() for _ in chunks]


# --- helpers -------------------------------------------------------------


_STUB_PAGES = [
    RenderedPage(page_number=1, data=b"jpeg-1", width=400, height=560, content_type="image/jpeg"),
    RenderedPage(page_number=2, data=b"jpeg-2", width=400, height=560, content_type="image/jpeg"),
]


@pytest.fixture(autouse=True)
def _stub_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub PDF rasterisation so the thumbnails stage needs neither poppler nor a real PDF."""
    monkeypatch.setattr(service_module, "render_thumbnails", lambda _pdf: _STUB_PAGES)


def _factory(conn: AsyncConnection):
    @asynccontextmanager
    async def factory() -> AsyncIterator[UnitOfWork]:
        yield UnitOfWork(conn)

    return factory


async def _document(
    conn: AsyncConnection,
    doc_type: DocumentType,
    file_name: str = "p.pdf",
    form_role: FormRole | None = None,
) -> tuple[UUID, UUID]:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-ING",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=doc_type,
            file_name=file_name,
            number_of_pages=1,
            form_role=form_role,
        )
    )
    return project.project_uuid, doc.document_uuid


# GAEB D83 fixture: OZ mask '1P' (one hierarchy digit, one position digit), so raw OZ '11'
# reads as '1.1'. positions are (raw_oz, menge as 11 digits, kurztext).


def _d83_record(body: str) -> str:
    return body.ljust(74) + "000000"


def _d83_bytes(positions: list[tuple[str, str, str]]) -> bytes:
    lines = [
        _d83_record(f"00{'':8}83L".ljust(62) + "1P".ljust(9) + "90"),
        _d83_record(f"111{'':8}N"),
        _d83_record("12Strassenbau"),
    ]
    for oz, menge, kurztext in positions:
        body = f"21{oz:<9}NNN".ljust(23) + menge + "m".ljust(4)
        lines.append(_d83_record(body.ljust(43) + "21109"))
        lines.append(_d83_record(f"25{kurztext}"))
        lines.append(_d83_record(f"26   {kurztext} im Detail."))
    lines.append(_d83_record("31"))
    lines.append(_d83_record("99"))
    return "\n".join(lines).encode("cp850")


# --- tests ---------------------------------------------------------------


async def test_gaeb_document_parses_into_lv_items_and_chunks(conn: AsyncConnection) -> None:
    project_uuid, document_uuid = await _document(
        conn, DocumentType.LV_DOCUMENT, file_name="p.d83"
    )
    search = _RecordingSearch()
    langchain = _FakeLangchain()
    storage = _FakeStorage(_d83_bytes([("11", "00000025000", "Oberboden abtragen")]))
    service = IngestionService(
        _factory(conn), storage, search, _FakeEmbeddings(), langchain  # type: ignore[arg-type]
    )

    result = await service.ingest_document(document_uuid)

    # The GAEB short path skips every PDF stage.
    assert result.source_lines == 0
    assert result.thumbnails == 0
    assert result.langchain_chunks == 0
    assert result.document_chunks == 0
    assert langchain.calls == []
    assert storage.puts == []
    assert result.lv_items == 2 and result.lv_chunks == 2

    repo = LVItemRepository(conn)
    item = await repo.get_by_project_and_oz(project_uuid, "1.1")
    assert item is not None
    assert item.menge == Decimal("25") and item.stl_nr == "21109"
    assert item.kurztext == "Oberboden abtragen"
    assert item.source_lines == []
    titel = await repo.get_by_project_and_oz(project_uuid, "1")
    assert titel is not None and titel.positionstyp == "Titel"

    assert all(c.source_doc_type == SourceDocType.LV_ITEM for c in search.indexed)
    assert any(c.oz == "1.1" and c.stl_nr == "21109" for c in search.indexed)


async def test_prose_document_runs_common_stages(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project_uuid, document_uuid = await _document(conn, DocumentType.PROSE_DOCUMENT)
    monkeypatch.setattr(
        service_module,
        "extract_source_lines",
        lambda _b, doc: [
            NewSourceLine(document_uuid=doc, line_id=0, page=1, bbox=(0, 0, 1, 1), line_text="prose body")
        ],
    )
    search = _RecordingSearch()
    service = IngestionService(
        _factory(conn), _FakeStorage(), search, _FakeEmbeddings(), _FakeLangchain()  # type: ignore[arg-type]
    )

    result = await service.ingest_document(document_uuid)

    assert result.lv_items == 0 and result.lv_chunks == 0
    assert result.document_chunks >= 1
    assert all(SourceDocType.LV_ITEM not in c[1] for c in search.calls if c[0] == "index")


def _form_pdf() -> bytes:
    return acroform_pdf(
        [
            text_field("Vergabenummer", 700, "26/001"),
            text_field("Ort", 680, "Berlin"),
            FieldSpec("Teilnahme", "/Btn", (50, 600, 60, 610), "/Yes", tool_tip="Teilnahme"),
        ]
    )


async def test_form_document_extracts_fields_and_indexes_form_chunks(
    conn: AsyncConnection,
) -> None:
    project_uuid, document_uuid = await _document(
        conn, DocumentType.FORM_DOCUMENT, "FB 312-B.pdf", FormRole.VERGABESTELLE
    )
    search = _RecordingSearch()
    langchain = _FakeLangchain()
    service = IngestionService(
        _factory(conn), _FakeStorage(_form_pdf()), search, _FakeEmbeddings(), langchain  # type: ignore[arg-type]
    )

    result = await service.ingest_document(document_uuid)

    assert langchain.calls == []
    assert result.langchain_chunks == 0
    assert result.thumbnails == 2
    assert result.form_fields == 3
    assert result.document_chunks >= 1
    assert {c.source_doc_type for c in search.indexed} == {SourceDocType.FORM}
    assert {c.project_uuid for c in search.indexed} == {project_uuid}
    assert ("archive", (document_uuid, SourceDocType.FORM)) in search.calls
    assert search.indexed[0].chunk_text == "## Seite 1\nTeilnahme"
    fields = await FormFieldRepository(conn).list_for_document(document_uuid)
    assert [(f.name, f.value) for f in fields] == [
        ("Vergabenummer", "26/001"),
        ("Ort", "Berlin"),
        ("Teilnahme", "ja"),
    ]
    lines = await SourceLineRepository(conn).list_by_document(document_uuid)
    assert [line.line_text for line in lines] == ["## Seite 1", "[x] Teilnahme"]


async def test_flattened_form_indexes_only_checked_options(
    conn: AsyncConnection,
) -> None:
    project_uuid, document_uuid = await _document(
        conn,
        DocumentType.FORM_DOCUMENT,
        "00 - Aufforderung zur Angebotsabgabe.pdf",
        FormRole.VERGABESTELLE,
    )
    search = _RecordingSearch()
    service = IngestionService(
        _factory(conn), _FakeStorage(hva_111_page()), search, _FakeEmbeddings(), _FakeLangchain()  # type: ignore[arg-type]
    )

    result = await service.ingest_document(document_uuid)

    assert result.form_fields == 6
    assert {c.source_doc_type for c in search.indexed} == {SourceDocType.FORM}
    assert {c.project_uuid for c in search.indexed} == {project_uuid}
    texts = [c.chunk_text for c in search.indexed]
    assert "## 6 Nebenangebote\n6.1 Nebenangebote sind nicht zugelassen" in texts
    assert "## 7 Angebotswertung:\nkeine Option angekreuzt" in texts
    assert not any("zugelassen\n" in t and "nicht" not in t for t in texts)
    assert not any("[ ]" in t or "[x]" in t or "nur für ein Los" in t for t in texts)
    fields = await FormFieldRepository(conn).list_for_document(document_uuid)
    assert [(f.section, f.label, f.value) for f in fields][:2] == [
        ("4 Losweise Vergabe:", "Nein", "ja"),
        ("4 Losweise Vergabe:", "Ja, Angebotsabgabe ist zugelassen", "nein"),
    ]
    lines = await SourceLineRepository(conn).list_by_document(document_uuid)
    assert "[ ] nur für ein Los" in [line.line_text for line in lines]


async def test_form_reingest_replaces_fields(conn: AsyncConnection) -> None:
    _project_uuid, document_uuid = await _document(
        conn, DocumentType.FORM_DOCUMENT, "x.pdf", FormRole.UNBEKANNT
    )
    service = IngestionService(
        _factory(conn), _FakeStorage(_form_pdf()), _RecordingSearch(), _FakeEmbeddings(), _FakeLangchain()  # type: ignore[arg-type]
    )

    await service.ingest_document(document_uuid)
    await service.ingest_document(document_uuid)

    fields = await FormFieldRepository(conn).list_for_document(document_uuid)
    assert [f.field_order for f in fields] == [0, 1, 2]


async def test_gaeb_reingest_is_idempotent(conn: AsyncConnection) -> None:
    project_uuid, document_uuid = await _document(
        conn, DocumentType.LV_DOCUMENT, file_name="p.d83"
    )
    first = _d83_bytes(
        [
            ("11", "00000025000", "Oberboden abtragen"),
            ("12", "00000010000", "Mutterboden andecken"),
        ]
    )
    second = _d83_bytes(  # 1.1 menge changed, 1.2 dropped, 1.3 added
        [
            ("11", "00000099000", "Oberboden abtragen"),
            ("13", "00000005000", "Pflaster verlegen"),
        ]
    )
    search = _RecordingSearch()
    storage = _FakeStorage(first)
    service = IngestionService(
        _factory(conn), storage, search, _FakeEmbeddings(), _FakeLangchain()  # type: ignore[arg-type]
    )
    repo = LVItemRepository(conn)

    await service.ingest_document(document_uuid)
    item_11_before = await repo.get_by_project_and_oz(project_uuid, "1.1")
    item_12_before = await repo.get_by_project_and_oz(project_uuid, "1.2")
    assert item_11_before is not None and item_12_before is not None
    search.calls.clear()

    # Re-ingest the same document: no (document_uuid, oz) collision, in-place updates.
    storage.data = second
    result = await service.ingest_document(document_uuid)

    assert result.lv_items == 3  # 1, 1.1, 1.3
    item_11_after = await repo.get_by_project_and_oz(project_uuid, "1.1")
    assert item_11_after is not None
    assert item_11_after.lv_item_uuid == item_11_before.lv_item_uuid  # stable uuid
    assert item_11_after.menge == Decimal("99")  # updated in place
    assert await repo.get_by_project_and_oz(project_uuid, "1.2") is None  # dropped
    assert await repo.get_by_project_and_oz(project_uuid, "1.3") is not None  # added
    assert {i.oz for i in await repo.list_by_project(project_uuid)} == {"1", "1.1", "1.3"}

    # One archive for the whole re-ingest: the survivors' stable uuids plus the dropped
    # position's, so its LV_ITEM chunks leave the live index too.
    archives = [c[1] for c in search.calls if c[0] == "archive"]
    assert len(archives) == 1
    archived_uuids, archived_type = archives[0]
    assert archived_type is SourceDocType.LV_ITEM
    assert item_12_before.lv_item_uuid in archived_uuids
    assert item_11_before.lv_item_uuid in archived_uuids
    assert len(search.indexed) > 0
    assert len([c for c in search.calls if c[0] == "index"]) == 1


async def test_thumbnails_rendered_stored_and_persisted(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project_uuid, document_uuid = await _document(conn, DocumentType.PROSE_DOCUMENT)
    monkeypatch.setattr(
        service_module,
        "extract_source_lines",
        lambda _b, doc: [
            NewSourceLine(document_uuid=doc, line_id=0, page=1, bbox=(0, 0, 1, 1), line_text="x")
        ],
    )
    storage = _FakeStorage()
    service = IngestionService(
        _factory(conn), storage, _RecordingSearch(), _FakeEmbeddings(), _FakeLangchain()  # type: ignore[arg-type]
    )

    result = await service.ingest_document(document_uuid)

    assert result.thumbnails == 2
    rows = await ThumbnailRepository(conn).list_by_document(document_uuid)
    assert [r.page_number for r in rows] == [1, 2]
    assert rows[0].object_key == thumbnail_object_key(document_uuid, 1)
    assert rows[0].bucket == "test-bucket"
    assert rows[0].width == 400 and rows[0].height == 560
    assert rows[0].content_type == "image/jpeg"
    # Each page's image was written to object storage under its thumbnail key.
    assert storage.puts == [
        (thumbnail_object_key(document_uuid, 1), "image/jpeg"),
        (thumbnail_object_key(document_uuid, 2), "image/jpeg"),
    ]


async def test_progress_events_persisted_and_logged(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _project_uuid, document_uuid = await _document(conn, DocumentType.PROSE_DOCUMENT)
    monkeypatch.setattr(
        service_module,
        "extract_source_lines",
        lambda _b, doc: [
            NewSourceLine(document_uuid=doc, line_id=0, page=1, bbox=(0, 0, 1, 1), line_text="x")
        ],
    )
    job = await IngestJobRepository(conn).add(NewIngestJob(document_uuid=document_uuid))
    langchain = _FakeLangchain()
    service = IngestionService(
        _factory(conn), _FakeStorage(), _RecordingSearch(), _FakeEmbeddings(), langchain  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO, logger="shared.services.ingestion.progress"):
        await service.ingest_document(document_uuid, job_uuid=job.job_uuid)

    # The langchain ingestor receives the job uuid so its embedding usage is attributed to the job.
    assert len(langchain.calls) == 1
    assert langchain.calls[0][0] == document_uuid
    assert langchain.calls[0][2] == job.job_uuid

    # Every milestone is persisted as a job event (ts ties within one test txn, so compare the set).
    events = await IngestJobEventRepository(conn).list_for_job(job.job_uuid)
    assert {e.event for e in events} == {
        "started",
        "thumbnails_generated",
        "langchain_chunks_indexed",
        "source_lines_persisted",
        "document_chunks_indexed",
        "completed",
    }
    # ...and mirrored to the logger the harness routes to stdout.
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "started" in logged and "completed" in logged


async def test_gaeb_progress_events_persisted(conn: AsyncConnection) -> None:
    _project_uuid, document_uuid = await _document(
        conn, DocumentType.LV_DOCUMENT, file_name="p.d83"
    )
    job = await IngestJobRepository(conn).add(NewIngestJob(document_uuid=document_uuid))
    storage = _FakeStorage(_d83_bytes([("11", "00000001000", "Eins")]))
    service = IngestionService(
        _factory(conn), storage, _RecordingSearch(), _FakeEmbeddings(), _FakeLangchain()  # type: ignore[arg-type]
    )

    await service.ingest_document(document_uuid, job_uuid=job.job_uuid)

    events = await IngestJobEventRepository(conn).list_for_job(job.job_uuid)
    assert {e.event for e in events} == {"started", "lv_items_indexed", "completed"}


async def test_missing_document_raises(conn: AsyncConnection) -> None:
    search = _RecordingSearch()
    service = IngestionService(
        _factory(conn), _FakeStorage(), search, _FakeEmbeddings(), _FakeLangchain()  # type: ignore[arg-type]
    )
    with pytest.raises(service_module.DocumentNotFoundError):
        await service.ingest_document(uuid4())


async def test_failed_stage_records_failure_event(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project_uuid, document_uuid = await _document(conn, DocumentType.PROSE_DOCUMENT)
    job = await IngestJobRepository(conn).add(NewIngestJob(document_uuid=document_uuid))

    def _boom(_b: bytes, _doc: UUID) -> list[NewSourceLine]:
        raise RuntimeError("extract exploded")

    monkeypatch.setattr(service_module, "extract_source_lines", _boom)
    service = IngestionService(
        _factory(conn), _FakeStorage(), _RecordingSearch(), _FakeEmbeddings(), _FakeLangchain()  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError):
        await service.ingest_document(document_uuid, job_uuid=job.job_uuid)

    events = await IngestJobEventRepository(conn).list_for_job(job.job_uuid)
    failed = [e for e in events if e.event == "failed"]
    assert len(failed) == 1
    # Failure names the phase it broke in (EXTRACT) and carries the exception text.
    assert failed[0].pipeline_phase == "extract"
    assert "extract exploded" in failed[0].message
