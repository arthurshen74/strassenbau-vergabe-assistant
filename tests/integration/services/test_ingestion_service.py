from __future__ import annotations

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
from shared.models.enums import DocumentType, SourceDocType
from shared.models.llm_output_schemas import LVExtraction, LVPosition
from shared.models.project import NewProject
from shared.models.simple_chunk import NewSimpleChunk
from shared.models.source_line import NewSourceLine
from shared.repositories.documents import DocumentRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.source_lines import SourceLineRepository
from shared.repositories.thumbnails import ThumbnailRepository
from shared.services.ingestion import IngestionService
from shared.services.ingestion import ingestion_service as service_module
from shared.services.ingestion.thumbnails import RenderedPage

# --- fakes ---------------------------------------------------------------


class _FakeStorage:
    bucket = "test-bucket"

    def __init__(self) -> None:
        self.puts: list[tuple[str, str]] = []

    def get_object(self, key: str) -> bytes:
        return b"%PDF-fake"

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.puts.append((key, content_type))


class _FakeEmbeddings:
    async def embed(
        self, texts: list[str], *, project_uuid: Any = None, ingest_job_uuid: Any = None
    ) -> list[list[float]]:
        return [[float(i)] for i in range(len(texts))]


class _RecordingSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.indexed: list[NewSimpleChunk] = []

    async def archive_source(self, source_doc_uuid: UUID, source_doc_type: SourceDocType) -> int:
        self.calls.append(("archive", (source_doc_uuid, source_doc_type)))
        return 0

    async def index_chunks(self, chunks: list[NewSimpleChunk], *, refresh: bool = False) -> list[UUID]:
        self.calls.append(("index", [c.source_doc_type for c in chunks]))
        self.indexed.extend(chunks)
        return [uuid4() for _ in chunks]


class _FakePrompts:
    def __init__(self, *extractions: LVExtraction) -> None:
        self._extractions = list(extractions)
        self.called = False
        self.calls = 0

    async def run_lv_extraction(self, numbered_document: str, **_: Any) -> LVExtraction:
        self.called = True
        # Successive calls return successive extractions; the last one repeats.
        extraction = self._extractions[min(self.calls, len(self._extractions) - 1)]
        self.calls += 1
        return extraction


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


async def _document(conn: AsyncConnection, doc_type: DocumentType) -> tuple[UUID, UUID]:
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
            file_name="p.pdf",
            number_of_pages=1,
        )
    )
    return project.project_uuid, doc.document_uuid


def _lv_lines(document_uuid: UUID) -> list[NewSourceLine]:
    texts = ["1 Strassenbau", "1.1 StL-Nr.: 21 109", "Oberboden abtragen", "25,00 m"]
    return [
        NewSourceLine(document_uuid=document_uuid, line_id=i, page=1, bbox=(0, 0, 1, 1), line_text=t)
        for i, t in enumerate(texts)
    ]


def _lv_extraction() -> LVExtraction:
    return LVExtraction(
        positions=[
            LVPosition(
                oz="1", is_title=True, kurztext_line=0,
                langtext_start=-1, langtext_end=-1, hinweis_start=-1, hinweis_end=-1,
                stl_nr=None, menge=None, einheit=None, linked_oz=None, positionstyp=None,
            ),
            LVPosition(
                oz="1.1", is_title=False, kurztext_line=1,
                langtext_start=2, langtext_end=2, hinweis_start=-1, hinweis_end=-1,
                stl_nr="21 109", menge="25,00", einheit="m", linked_oz=None, positionstyp=None,
            ),
        ]
    )


# --- tests ---------------------------------------------------------------


async def test_lv_document_runs_common_and_lv_branches(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_uuid, document_uuid = await _document(conn, DocumentType.LV_DOCUMENT)
    monkeypatch.setattr(
        service_module, "extract_source_lines", lambda _b, doc: _lv_lines(doc)
    )
    search = _RecordingSearch()
    prompts = _FakePrompts(_lv_extraction())
    service = IngestionService(
        _factory(conn), _FakeStorage(), search, _FakeEmbeddings(), prompts  # type: ignore[arg-type]
    )

    result = await service.ingest_document(document_uuid)

    assert prompts.called
    assert result.source_lines == 4
    assert result.document_chunks >= 1
    assert result.lv_items == 2 and result.lv_chunks == 2

    persisted = await SourceLineRepository(conn).list_by_document(document_uuid)
    assert len(persisted) == 4

    item = await LVItemRepository(conn).get_by_project_and_oz(project_uuid, "1.1")
    assert item is not None
    assert item.menge == Decimal("25") and item.stl_nr == "21 109"
    assert item.langtext == "Oberboden abtragen"
    titel = await LVItemRepository(conn).get_by_project_and_oz(project_uuid, "1")
    assert titel is not None and titel.positionstyp == "Titel"

    # DOCUMENT chunks are indexed before any LV_ITEM chunks.
    index_types = [c[1] for c in search.calls if c[0] == "index"]
    assert index_types[0] == [SourceDocType.DOCUMENT]
    assert any(SourceDocType.LV_ITEM in types for types in index_types[1:])
    lv_chunks = [c for c in search.indexed if c.source_doc_type == SourceDocType.LV_ITEM]
    assert any(c.oz == "1.1" and c.stl_nr == "21 109" for c in lv_chunks)


async def test_prose_document_skips_lv_branch(
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
    prompts = _FakePrompts(_lv_extraction())
    service = IngestionService(
        _factory(conn), _FakeStorage(), search, _FakeEmbeddings(), prompts  # type: ignore[arg-type]
    )

    result = await service.ingest_document(document_uuid)

    assert not prompts.called
    assert result.lv_items == 0 and result.lv_chunks == 0
    assert result.document_chunks >= 1
    assert all(SourceDocType.LV_ITEM not in c[1] for c in search.calls if c[0] == "index")


def _reingest_lines(document_uuid: UUID) -> list[NewSourceLine]:
    texts = [
        "1 Strassenbau",
        "1.1 StL-Nr.: 21 109",
        "Oberboden abtragen",
        "1.2",
        "Mutterboden andecken",
        "1.3",
        "Pflaster verlegen",
    ]
    return [
        NewSourceLine(document_uuid=document_uuid, line_id=i, page=1, bbox=(0, 0, 1, 1), line_text=t)
        for i, t in enumerate(texts)
    ]


def _pos(
    oz: str, kurztext_line: int, *, is_title: bool = False,
    langtext: tuple[int, int] | None = None, menge: str | None = None,
) -> LVPosition:
    return LVPosition(
        oz=oz, is_title=is_title, kurztext_line=kurztext_line,
        langtext_start=langtext[0] if langtext else -1,
        langtext_end=langtext[1] if langtext else -1,
        hinweis_start=-1, hinweis_end=-1, stl_nr="21 109" if oz == "1.1" else None,
        menge=menge, einheit="m" if menge else None, linked_oz=None, positionstyp=None,
    )


async def test_reingest_is_idempotent(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_uuid, document_uuid = await _document(conn, DocumentType.LV_DOCUMENT)
    monkeypatch.setattr(service_module, "extract_source_lines", lambda _b, doc: _reingest_lines(doc))

    first = LVExtraction(positions=[
        _pos("1", 0, is_title=True),
        _pos("1.1", 1, langtext=(2, 2), menge="25,00"),
        _pos("1.2", 3, langtext=(4, 4), menge="10,00"),
    ])
    second = LVExtraction(positions=[  # 1.1 menge changed, 1.2 dropped, 1.3 added
        _pos("1", 0, is_title=True),
        _pos("1.1", 1, langtext=(2, 2), menge="99,00"),
        _pos("1.3", 5, langtext=(6, 6), menge="5,00"),
    ])
    search = _RecordingSearch()
    service = IngestionService(
        _factory(conn), _FakeStorage(), search, _FakeEmbeddings(), _FakePrompts(first, second)  # type: ignore[arg-type]
    )
    repo = LVItemRepository(conn)

    await service.ingest_document(document_uuid)
    item_11_before = await repo.get_by_project_and_oz(project_uuid, "1.1")
    item_12_before = await repo.get_by_project_and_oz(project_uuid, "1.2")
    assert item_11_before is not None and item_12_before is not None

    # Re-ingest the same document: no (document_uuid, oz) collision, in-place updates.
    result = await service.ingest_document(document_uuid)

    assert result.lv_items == 3  # 1, 1.1, 1.3
    item_11_after = await repo.get_by_project_and_oz(project_uuid, "1.1")
    assert item_11_after is not None
    assert item_11_after.lv_item_uuid == item_11_before.lv_item_uuid  # stable uuid
    assert item_11_after.menge == Decimal("99")  # updated in place
    assert await repo.get_by_project_and_oz(project_uuid, "1.2") is None  # dropped
    assert await repo.get_by_project_and_oz(project_uuid, "1.3") is not None  # added
    assert {i.oz for i in await repo.list_by_project(project_uuid)} == {"1", "1.1", "1.3"}

    # The dropped position's LV_ITEM chunks were archived out of the live index.
    assert ("archive", (item_12_before.lv_item_uuid, SourceDocType.LV_ITEM)) in search.calls


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
        _factory(conn), storage, _RecordingSearch(), _FakeEmbeddings(), _FakePrompts(_lv_extraction())  # type: ignore[arg-type]
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


async def test_missing_document_raises(conn: AsyncConnection) -> None:
    search = _RecordingSearch()
    service = IngestionService(
        _factory(conn), _FakeStorage(), search, _FakeEmbeddings(), _FakePrompts(_lv_extraction())  # type: ignore[arg-type]
    )
    with pytest.raises(service_module.DocumentNotFoundError):
        await service.ingest_document(uuid4())
