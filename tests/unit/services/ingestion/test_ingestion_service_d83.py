"""The GAEB D83 branch of IngestionService.

A `.d83` document must parse straight into LV items and LV_ITEM chunks plus LV texts
(Vorbemerkungen, Hinweise) and LV_TEXT chunks -- no thumbnails, no source lines, no
DOCUMENT chunks, and no LLM call (prompts/langchain collaborators are None here, so
touching them would fail loudly). Each source type goes through one embeddings call,
one archive call, and one bulk index for the whole document, however many items it
has.
"""

from __future__ import annotations

from collections.abc import Sequence
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


def _d83_bytes(positions: list[tuple[str, str]]) -> bytes:
    """A D83 file with a Vorbemerkung T-block, OZ mask '11PPPP', and one Titel carrying
    a Hinweis; positions are (raw_oz, kurztext)."""
    lines = [
        _record("T0"),
        _record("T1Vorbemerkung: es gilt die VOB/B."),
        _record("T9"),
        _record(f"00{'':8}83L".ljust(62) + "11PPPP90"),
        _record("1101       N"),
        _record("12Erdarbeiten"),
        _record("20"),
        _record("26   Hinweis zu Titel 01."),
    ]
    for oz, kurztext in positions:
        lines.append(_record(f"21{oz:<9}NN N".ljust(23) + "00000002500" + "m3"))
        lines.append(_record(f"25{kurztext}"))
        lines.append(_record(f"26   {kurztext} und seitlich lagern."))
    lines.append(_record("31"))
    lines.append(_record("99"))
    return "\n".join(lines).encode("cp850")


D83_BYTES = _d83_bytes([("010001", "Oberboden abtragen")])


class _FakeStorage:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.requested: list[str] = []

    def get_object(self, key: str) -> bytes:
        self.requested.append(key)
        return self.data


class _RecordingEmbeddings:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(i)] for i in range(len(texts))]


class _RecordingSearch:
    def __init__(self) -> None:
        self.archived: list[tuple[set[UUID], SourceDocType]] = []
        self.index_calls: list[list[NewSimpleChunk]] = []

    async def archive_sources(
        self, source_doc_uuids: Sequence[UUID], source_doc_type: SourceDocType
    ) -> int:
        self.archived.append((set(source_doc_uuids), source_doc_type))
        return 0

    async def index_chunks(self, chunks: list[NewSimpleChunk]) -> list[UUID]:
        self.index_calls.append(list(chunks))
        return [uuid4() for _ in chunks]

    @property
    def indexed(self) -> list[NewSimpleChunk]:
        return [chunk for call in self.index_calls for chunk in call]


class _FakeDocumentRepo:
    def __init__(self, document: Document) -> None:
        self.document = document

    async def get(self, document_uuid: UUID) -> Document | None:
        return self.document if document_uuid == self.document.document_uuid else None


class _FakeLVItemRepo:
    def __init__(self) -> None:
        self.added: list[NewLVItem] = []
        self.items: list[LVItem] = []
        self.kept_ozs: list[str] = []
        self.removed: list[UUID] = []

    async def add_many(self, items: list[NewLVItem]) -> list[LVItem]:
        self.added = list(items)
        now = datetime.now(tz=UTC)
        self.items = [
            LVItem(lv_item_uuid=uuid4(), last_ingestion=now, **item.model_dump())
            for item in items
        ]
        return self.items

    async def delete_missing(
        self, document_uuid: UUID, keep_ozs: list[str]
    ) -> list[UUID]:
        self.kept_ozs = list(keep_ozs)
        return list(self.removed)


class _FakeLVTextRepo:
    def __init__(self) -> None:
        self.replaced: list[NewLVText] = []
        self.texts: list[LVText] = []

    async def replace(
        self, document_uuid: UUID, texts: list[NewLVText]
    ) -> tuple[list[LVText], list[UUID]]:
        self.replaced = list(texts)
        now = datetime.now(tz=UTC)
        self.texts = [
            LVText(lv_text_uuid=uuid4(), last_ingestion=now, **t.model_dump())
            for t in texts
        ]
        return self.texts, []


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


def _document() -> Document:
    return Document(
        document_uuid=uuid4(),
        project_uuid=uuid4(),
        document_type=DocumentType.LV_DOCUMENT,
        file_name="P22039_LV1.D83",
        number_of_pages=0,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


def _service(
    document: Document,
    lv_repo: _FakeLVItemRepo,
    text_repo: _FakeLVTextRepo,
    storage: _FakeStorage,
) -> tuple[IngestionService, _RecordingEmbeddings, _RecordingSearch]:
    uow = _FakeUow(_FakeDocumentRepo(document), lv_repo, text_repo)

    @asynccontextmanager
    async def uow_factory():  # noqa: ANN202
        yield uow

    embeddings = _RecordingEmbeddings()
    search = _RecordingSearch()
    service = IngestionService(
        uow_factory,  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        search,  # type: ignore[arg-type]
        embeddings,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )
    return service, embeddings, search


async def test_d83_document_ingests_lv_items_without_pdf_stages() -> None:
    document = _document()
    lv_repo = _FakeLVItemRepo()
    text_repo = _FakeLVTextRepo()
    service, embeddings, search = _service(
        document, lv_repo, text_repo, _FakeStorage(D83_BYTES)
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

    # Per source type: one embeddings call, one archive covering every source, one
    # bulk index. Items go first, then texts.
    assert [len(call) for call in embeddings.calls] == [2, 2]
    assert search.archived == [
        ({item.lv_item_uuid for item in lv_repo.items}, SourceDocType.LV_ITEM),
        ({text.lv_text_uuid for text in text_repo.texts}, SourceDocType.LV_TEXT),
    ]
    assert len(search.index_calls) == 2


async def test_multi_item_d83_batches_one_embed_archive_and_index() -> None:
    document = _document()
    lv_repo = _FakeLVItemRepo()
    text_repo = _FakeLVTextRepo()
    storage = _FakeStorage(
        _d83_bytes(
            [
                ("010001", "Oberboden abtragen"),
                ("010002", "Mutterboden andecken"),
                ("010003", "Pflaster verlegen"),
            ]
        )
    )
    service, embeddings, search = _service(document, lv_repo, text_repo, storage)

    result = await service.ingest_document(document.document_uuid)

    assert result.lv_items == 4  # Titel + 3 positions
    assert result.lv_texts == 2
    assert result.lv_chunks == 6
    assert [len(call) for call in embeddings.calls] == [4, 2]
    assert len(search.index_calls) == 2
    item_chunks, text_chunks = search.index_calls
    assert {chunk.oz for chunk in item_chunks} == {
        "01",
        "01.0001",
        "01.0002",
        "01.0003",
    }
    assert {chunk.source_doc_uuid for chunk in item_chunks} == {
        item.lv_item_uuid for item in lv_repo.items
    }
    assert {chunk.source_doc_uuid for chunk in text_chunks} == {
        text.lv_text_uuid for text in text_repo.texts
    }
    assert search.archived == [
        ({item.lv_item_uuid for item in lv_repo.items}, SourceDocType.LV_ITEM),
        ({text.lv_text_uuid for text in text_repo.texts}, SourceDocType.LV_TEXT),
    ]

    # Re-ingest with one position dropped: its uuid joins the survivors in the single
    # LV_ITEM archive call.
    removed_uuid = uuid4()
    lv_repo.removed = [removed_uuid]
    storage.data = _d83_bytes(
        [("010001", "Oberboden abtragen"), ("010003", "Pflaster verlegen")]
    )
    embeddings.calls.clear()
    search.archived.clear()
    search.index_calls.clear()

    result = await service.ingest_document(document.document_uuid)

    assert result.lv_items == 3
    assert [len(call) for call in embeddings.calls] == [3, 2]
    assert len(search.index_calls) == 2
    assert len(search.archived) == 2
    archived_uuids, archived_type = search.archived[0]
    assert archived_type is SourceDocType.LV_ITEM
    assert archived_uuids == {item.lv_item_uuid for item in lv_repo.items} | {
        removed_uuid
    }
