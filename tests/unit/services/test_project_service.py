from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from uuid import UUID, uuid4

from shared.models.document import Document, NewDocument
from shared.models.enums import DocumentType
from shared.services.project_service import (
    ProjectService,
    UploadInput,
    _classify_document_type,
    _count_pdf_pages,
    _expand_zip,
)


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_expand_zip_flattens_paths_and_skips_junk() -> None:
    data = _zip(
        {
            "a.pdf": b"x",
            "sub/dir/b.txt": b"y",  # nested -> basename only
            "__MACOSX/c": b"z",  # macOS junk -> skipped
            ".DS_Store": b"q",  # dotfile -> skipped
        }
    )
    out = _expand_zip(data)
    assert sorted(u.file_name for u in out) == ["a.pdf", "b.txt"]


def test_count_pdf_pages_non_pdf_is_zero() -> None:
    assert _count_pdf_pages(UploadInput("notes.txt", "text/plain", b"hello")) == 0


def test_classify_document_type_gaeb_is_lv() -> None:
    assert _classify_document_type("anything.d83") == DocumentType.LV_DOCUMENT
    assert _classify_document_type("P22039_LV1.D83") == DocumentType.LV_DOCUMENT
    assert _classify_document_type("projekt_lv.x83") == DocumentType.LV_DOCUMENT
    assert (
        _classify_document_type("P630394379990126_LV.X83") == DocumentType.LV_DOCUMENT
    )


def test_classify_document_type_prose_for_everything_else() -> None:
    # The LV print-layout PDF is prose too: LV items come from GAEB files only.
    assert _classify_document_type("Projekt_LV1.pdf") == DocumentType.PROSE_DOCUMENT
    assert _classify_document_type("Projekt_LV1.txt") == DocumentType.PROSE_DOCUMENT
    assert _classify_document_type("anhang.pdf") == DocumentType.PROSE_DOCUMENT


def _document(
    project_uuid: UUID,
    file_name: str = "doc.pdf",
    document_type: DocumentType = DocumentType.PROSE_DOCUMENT,
) -> Document:
    now = datetime.now(tz=UTC)
    return Document(
        document_uuid=uuid4(),
        project_uuid=project_uuid,
        document_type=document_type,
        file_name=file_name,
        number_of_pages=0,
        created_at=now,
        updated_at=now,
    )


class _FakeDocuments:
    def __init__(self, existing: list[Document] | None = None) -> None:
        self.documents = list(existing or [])
        self.deleted: list[UUID] = []

    async def add(self, new: NewDocument) -> Document:
        now = datetime.now(tz=UTC)
        doc = Document(
            document_uuid=uuid4(),
            created_at=now,
            updated_at=now,
            **new.model_dump(),
        )
        self.documents.append(doc)
        return doc

    async def delete(self, document_uuid: UUID) -> None:
        self.deleted.append(document_uuid)


class _FakeStorage:
    def __init__(self) -> None:
        self.put: list[str] = []
        self.deleted_keys: list[str] = []

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.put.append(key)

    def delete_objects(self, keys: list[str]) -> None:
        self.deleted_keys.extend(keys)


class _FakeIngestJobs:
    def __init__(self) -> None:
        self.added: list[UUID] = []

    async def add(self, new) -> None:  # noqa: ANN001 - mirrors the repo signature loosely
        self.added.append(new.document_uuid)


def _service(documents: _FakeDocuments) -> ProjectService:
    return ProjectService(
        None,  # type: ignore[arg-type]
        documents,  # type: ignore[arg-type]
        _FakeIngestJobs(),  # type: ignore[arg-type]
        storage=_FakeStorage(),  # type: ignore[arg-type]
    )


def _lv_documents(documents: _FakeDocuments) -> list[Document]:
    return [
        d for d in documents.documents if d.document_type == DocumentType.LV_DOCUMENT
    ]


async def test_gaeb_upload_adds_second_lv_document() -> None:
    project_uuid = uuid4()
    existing = _document(project_uuid, "Projekt_LV.d83", DocumentType.LV_DOCUMENT)
    documents = _FakeDocuments([existing])
    service = _service(documents)

    created = await service.ingest_documents(
        project_uuid,
        [UploadInput("Projekt_LV.x83", "application/octet-stream", b"<GAEB/>")],
    )

    assert documents.deleted == []
    storage = service.storage
    assert isinstance(storage, _FakeStorage)
    assert storage.deleted_keys == []
    assert [d.document_type for d in created] == [DocumentType.LV_DOCUMENT]
    assert [d.file_name for d in _lv_documents(documents)] == [
        "Projekt_LV.d83",
        "Projekt_LV.x83",
    ]


async def test_lv_named_pdf_uploads_as_prose() -> None:
    project_uuid = uuid4()
    existing = _document(project_uuid, "Projekt_LV.d83", DocumentType.LV_DOCUMENT)
    documents = _FakeDocuments([existing])
    service = _service(documents)

    created = await service.ingest_documents(
        project_uuid,
        [UploadInput("Other_LV.pdf", "application/pdf", b"x")],
    )

    assert documents.deleted == []
    assert [d.document_type for d in created] == [DocumentType.PROSE_DOCUMENT]


async def test_zip_types_gaeb_as_lv_and_lv_named_pdf_as_prose() -> None:
    documents = _FakeDocuments()
    service = _service(documents)
    data = _zip({"Projekt_LV1.pdf": b"x", "Projekt_LV.d83": b"y"})

    created = await service.ingest_documents(
        uuid4(),
        [UploadInput("batch.zip", "application/zip", data)],
    )

    types = {d.file_name: d.document_type for d in created}
    assert types["Projekt_LV.d83"] == DocumentType.LV_DOCUMENT
    assert types["Projekt_LV1.pdf"] == DocumentType.PROSE_DOCUMENT


async def test_zip_with_two_gaeb_files_creates_two_lv_documents() -> None:
    documents = _FakeDocuments()
    service = _service(documents)
    data = _zip({"Los1.x83": b"a", "Los2.d83": b"b"})

    await service.ingest_documents(
        uuid4(),
        [UploadInput("batch.zip", "application/zip", data)],
    )

    assert sorted(d.file_name for d in _lv_documents(documents)) == [
        "Los1.x83",
        "Los2.d83",
    ]
