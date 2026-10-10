"""The GAEB D83 branch of IngestionService.

A `.d83` document must parse straight into LV items and LV_ITEM chunks plus LV texts
(Vorbemerkungen, Hinweise) and LV_TEXT chunks -- no thumbnails, no source lines, no
DOCUMENT chunks, and no LLM call (prompts/langchain collaborators are None here, so
touching them would fail loudly).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from shared.models.document import Document
from shared.models.enums import DocumentType, LVTextKind, SourceDocType
from shared.models.lv_item import LVItem, NewLVItem
from shared.models.lv_text import LVText, NewLVText
from shared.models.simple_chunk import NewSimpleChunk
from shared.services.ingestion.ingestion_service import IngestionService


def _record(body: str) -> str:
    return body.ljust(74) + "000000"


D83_BYTES = "\n".join(
    [
        _record("T0"),
        _record("T1Vorbemerkung: es gilt die VOB/B."),
        _record("T9"),
        _record(f"00{'':8}83L".ljust(62) + "11PPPP90"),
        _record("1101       N"),
        _record("12Erdarbeiten"),
        _record("20"),
        _record("26   Hinweis zu Titel 01."),
        _record("21010001   NN N".ljust(23) + "00000002500" + "m3"),
        _record("25Oberboden abtragen"),
        _record("26   Oberboden abtragen und seitlich lagern."),
        _record("31"),
        _record("99"),
    ]
).encode("cp850")


class _FakeStorage:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.requested: list[str] = []

    def get_object(self, key: str) -> bytes:
        self.requested.append(key)
        return self.data


class _RecordingEmbeddings:
    async def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [[float(i)] for i in range(len(texts))]


class _RecordingSearch:
    def __init__(self) -> None:
        self.archived: list[tuple[UUID, SourceDocType]] = []
        self.indexed: list[NewSimpleChunk] = []

    async def archive_source(
        self, source_doc_uuid: UUID, source_doc_type: SourceDocType
    ) -> int:
        self.archived.append((source_doc_uuid, source_doc_type))
        return 0

    async def index_chunks(self, chunks: list[NewSimpleChunk]) -> list[UUID]:
        self.indexed.extend(chunks)
        return [uuid4() for _ in chunks]


class _FakeDocumentRepo:
    def __init__(self, document: Document) -> None:
        self.document = document

    async def get(self, document_uuid: UUID) -> Document | None:
        return self.document if document_uuid == self.document.document_uuid else None


class _FakeLVItemRepo:
    def __init__(self) -> None:
        self.added: list[NewLVItem] = []
        self.kept_ozs: list[str] = []

    async def add_many(self, items: list[NewLVItem]) -> list[LVItem]:
        self.added = list(items)
        now = datetime.now(tz=UTC)
        return [
            LVItem(lv_item_uuid=uuid4(), last_ingestion=now, **item.model_dump())
            for item in items
        ]

    async def delete_missing(
        self, document_uuid: UUID, keep_ozs: list[str]
    ) -> list[UUID]:
        self.kept_ozs = list(keep_ozs)
        return []


class _FakeLVTextRepo:
    def __init__(self) -> None:
        self.replaced: list[NewLVText] = []

    async def replace(
        self, document_uuid: UUID, texts: list[NewLVText]
    ) -> tuple[list[LVText], list[UUID]]:
        self.replaced = list(texts)
        now = datetime.now(tz=UTC)
        return [
            LVText(lv_text_uuid=uuid4(), last_ingestion=now, **t.model_dump())
            for t in texts
        ], []


class _FakeUow:
    def __init__(
        self,
        documents: _FakeDocumentRepo,
        lv_items: _FakeLVItemRepo,
        lv_texts: _FakeLVTextRepo,
    ) -> None:
        self.documents = documents
        self.lv_items = lv_items
        self.lv_texts = lv_texts
        self.ingest_job_events = None  # record_event no-ops for jobless runs


async def test_d83_document_ingests_lv_items_without_pdf_stages() -> None:
    document = Document(
        document_uuid=uuid4(),
        project_uuid=uuid4(),
        document_type=DocumentType.LV_DOCUMENT,
        file_name="P22039_LV1.D83",
        number_of_pages=0,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    lv_repo = _FakeLVItemRepo()
    text_repo = _FakeLVTextRepo()
    uow = _FakeUow(_FakeDocumentRepo(document), lv_repo, text_repo)

    @asynccontextmanager
    async def uow_factory():  # noqa: ANN202
        yield uow

    search = _RecordingSearch()
    service = IngestionService(
        uow_factory,  # type: ignore[arg-type]
        _FakeStorage(D83_BYTES),  # type: ignore[arg-type]
        search,  # type: ignore[arg-type]
        _RecordingEmbeddings(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )

    result = await service.ingest_document(document.document_uuid)

    assert result.source_lines == 0
    assert result.thumbnails == 0
    assert result.langchain_chunks == 0
    assert result.document_chunks == 0
    assert result.lv_items == 2  # Titel + position
    assert result.lv_texts == 2  # T-block Vortext + the Titel's Hinweis
    assert result.lv_chunks == 4  # one chunk per item and per text

    assert [item.oz for item in lv_repo.added] == ["01", "01.0001"]
    position = lv_repo.added[1]
    assert position.document_uuid == document.document_uuid
    assert position.menge == Decimal("2.500")
    assert position.einheit == "m3"
    assert position.source_lines == []
    assert position.hinweis == "Hinweis zu Titel 01."
    assert lv_repo.kept_ozs == ["01", "01.0001"]

    assert [(t.kind, t.placement, t.parent_oz, t.body) for t in text_repo.replaced] == [
        (LVTextKind.ADD_TEXT, "before", None, "Vorbemerkung: es gilt die VOB/B."),
        (LVTextKind.REMARK, None, "01", "Hinweis zu Titel 01."),
    ]

    by_type = {
        chunk.source_doc_type: [
            c for c in search.indexed if c.source_doc_type == chunk.source_doc_type
        ]
        for chunk in search.indexed
    }
    assert set(by_type) == {SourceDocType.LV_ITEM, SourceDocType.LV_TEXT}
    assert {c.oz for c in by_type[SourceDocType.LV_ITEM]} == {"01", "01.0001"}
    # A Hinweis chunk carries its LV-Gruppe as oz; a Vortext chunk has none.
    assert {c.oz for c in by_type[SourceDocType.LV_TEXT]} == {None, "01"}
    assert all(chunk.source_doc_pages == [] for chunk in search.indexed)
