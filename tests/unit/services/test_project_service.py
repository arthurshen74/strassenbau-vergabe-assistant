from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

import shared.services.project_service as project_service
from shared.config import settings
from shared.models.document import Document, NewDocument
from shared.models.enums import DocumentType, FormRole, IngestStatus
from shared.models.project import NewProject, Project
from shared.models.project_info_job import NewProjectInfoJob
from shared.services.project_service import (
    INGESTIBLE_SUFFIXES,
    ProjectService,
    UploadInput,
    ZipTooLargeError,
    _count_pdf_pages,
    classify_document,
    expand_zip,
)
from tests.form_pdfs import acroform_pdf, three_field_form


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
    out = expand_zip(data).uploads
    assert sorted(u.file_name for u in out) == ["a.pdf", "b.txt"]


def _nested(depth: int) -> bytes:
    """A zip nested `depth` levels deep with one PDF at the bottom."""
    data = _zip({"leaf.pdf": b"%PDF"})
    for level in range(depth - 1):
        data = _zip({f"level{level}.zip": data})
    return data


def test_expand_zip_flattens_nested_zips() -> None:
    inner = _zip({"deep/LV.x83": b"<GAEB/>"})
    middle = _zip({"inner.zip": inner, "Plan.pdf": b"%PDF"})
    data = _zip({"top.pdf": b"%PDF", "sub/middle.zip": middle})

    out = expand_zip(data)

    assert sorted(u.file_name for u in out.uploads) == ["LV.x83", "Plan.pdf", "top.pdf"]
    assert out.skipped == []


def test_expand_zip_normalises_backslash_paths() -> None:
    data = _zip({"Unterlagen\\Weitere Dokumente\\LV Los 1.x83": b"<GAEB/>"})
    assert [u.file_name for u in expand_zip(data).uploads] == ["LV Los 1.x83"]


def test_expand_zip_depth_cap() -> None:
    assert len(expand_zip(_nested(project_service.ZIP_MAX_DEPTH)).uploads) == 1
    with pytest.raises(ZipTooLargeError, match="ZIP_MAX_DEPTH"):
        expand_zip(_nested(project_service.ZIP_MAX_DEPTH + 1))


def test_expand_zip_entry_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project_service, "ZIP_MAX_ENTRIES", 3)
    expand_zip(_zip({f"{i}.pdf": b"x" for i in range(3)}))
    with pytest.raises(ZipTooLargeError, match="ZIP_MAX_ENTRIES"):
        expand_zip(_zip({f"{i}.pdf": b"x" for i in range(4)}))


def test_expand_zip_total_bytes_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project_service, "ZIP_MAX_TOTAL_BYTES", 1000)
    expand_zip(_zip({"a.pdf": b"x" * 1000}))
    # Counted across nesting levels: the nested zip's own size plus its contents.
    nested = _zip({"inner.zip": _zip({"b.pdf": b"x" * 600})})
    with pytest.raises(ZipTooLargeError, match="ZIP_MAX_TOTAL_BYTES"):
        expand_zip(nested)


def test_expand_zip_suffix_filter_records_skipped() -> None:
    inner = _zip({"notes.txt": b"n", "LV.d83": b"d"})
    data = _zip({"a.pdf": b"x", "docs/b.docx": b"y", "Los1.zip": inner})

    out = expand_zip(data, allowed_suffixes=INGESTIBLE_SUFFIXES)

    assert sorted(u.file_name for u in out.uploads) == ["LV.d83", "a.pdf"]
    assert out.skipped == ["docs/b.docx", "Los1.zip/notes.txt"]


def test_expand_zip_renames_basename_collisions() -> None:
    inner = _zip({"LV.pdf": b"4"})
    data = _zip(
        {
            "Los1/LV.pdf": b"1",
            "Los2/LV.pdf": b"2",
            "Los2/sub/Los2/LV.pdf": b"3",  # same parent name -> numbered
            "Los3.zip": inner,  # nested zip stem is the parent
        }
    )

    out = expand_zip(data)

    assert {u.file_name: u.data for u in out.uploads} == {
        "LV.pdf": b"1",
        "Los2__LV.pdf": b"2",
        "Los2__LV-2.pdf": b"3",
        "Los3__LV.pdf": b"4",
    }


def test_expand_zip_skips_corrupt_nested_zip() -> None:
    data = _zip({"a.pdf": b"x", "broken.zip": b"not a zip"})

    out = expand_zip(data)

    assert [u.file_name for u in out.uploads] == ["a.pdf"]
    assert out.skipped == ["broken.zip"]


def test_expand_zip_rejects_non_zip() -> None:
    with pytest.raises(zipfile.BadZipFile):
        expand_zip(b"x")


def test_count_pdf_pages_non_pdf_is_zero() -> None:
    assert _count_pdf_pages(UploadInput("notes.txt", "text/plain", b"hello")) == 0


LV = (DocumentType.LV_DOCUMENT, None, None)
PROSE = (DocumentType.PROSE_DOCUMENT, None, None)


@pytest.mark.parametrize(
    "file_name",
    ["anything.d83", "P22039_LV1.D83", "projekt_lv.x83", "P630394379990126_LV.X83"],
)
def test_classify_document_gaeb_is_lv(file_name: str) -> None:
    assert classify_document(file_name, b"<GAEB/>") == LV


def test_classify_document_prose_for_everything_else() -> None:
    # The LV print-layout PDF is prose too: LV items come from GAEB files only.
    assert classify_document("Projekt_LV1.pdf", b"%PDF") == PROSE
    assert classify_document("Projekt_LV1.txt", b"x") == PROSE
    assert classify_document("anhang.pdf", b"%PDF") == PROSE


def test_classify_document_zero_field_acroform_is_prose() -> None:
    assert classify_document("LV Los 1-3.pdf", acroform_pdf([])) == PROSE


def test_classify_document_fillable_pdf_is_a_form_with_role() -> None:
    data = three_field_form()
    assert classify_document("T1.1 FB 312-B Aufforderung.pdf", data) == (
        DocumentType.FORM_DOCUMENT,
        FormRole.VERGABESTELLE,
        "FB 312-B",
    )
    assert classify_document("Baustelleninformationsschild.pdf", data) == (
        DocumentType.FORM_DOCUMENT,
        FormRole.UNBEKANNT,
        None,
    )


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
        self.statuses: dict[UUID, IngestStatus] = {}

    async def add(self, new) -> None:  # noqa: ANN001 - mirrors the repo signature loosely
        self.added.append(new.document_uuid)
        self.statuses[new.document_uuid] = new.status


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


class _FakeProjects:
    def __init__(self) -> None:
        self.added: list[NewProject] = []

    async def add(self, new: NewProject) -> Project:
        self.added.append(new)
        now = datetime.now(tz=UTC)
        return Project(
            project_uuid=uuid4(), created_at=now, updated_at=now, **new.model_dump()
        )


class _FakeProjectInfoJobs:
    def __init__(self) -> None:
        self.added: list[NewProjectInfoJob] = []

    async def add(self, new: NewProjectInfoJob) -> None:
        self.added.append(new)


def _zip_service(documents: _FakeDocuments, projects: _FakeProjects) -> ProjectService:
    return ProjectService(
        projects,  # type: ignore[arg-type]
        documents,  # type: ignore[arg-type]
        _FakeIngestJobs(),  # type: ignore[arg-type]
        storage=_FakeStorage(),  # type: ignore[arg-type]
        project_info_jobs=_FakeProjectInfoJobs(),  # type: ignore[arg-type]
    )


async def test_create_from_zip_names_project_after_zip_stem() -> None:
    documents = _FakeDocuments()
    projects = _FakeProjects()
    service = _zip_service(documents, projects)
    data = _zip({"Los1.x83": b"a", "Los2.d83": b"b", "Plan.pdf": b"c", "x.txt": b"d"})

    result = await service.create_from_zip("uploads/2025007072.ZIP", data)

    assert [p.project_name for p in projects.added] == ["2025007072"]
    assert result.project.project_name == "2025007072"
    assert {d.file_name: d.document_type for d in result.documents} == {
        "Los1.x83": DocumentType.LV_DOCUMENT,
        "Los2.d83": DocumentType.LV_DOCUMENT,
        "Plan.pdf": DocumentType.PROSE_DOCUMENT,
    }
    assert result.skipped == ["x.txt"]
    ingest_jobs = service.ingest_jobs
    assert isinstance(ingest_jobs, _FakeIngestJobs)
    assert len(ingest_jobs.added) == 3
    info_jobs = service.project_info_jobs
    assert isinstance(info_jobs, _FakeProjectInfoJobs)
    assert [(j.language, j.overwrite) for j in info_jobs.added] == [
        (settings.project_info_language, True)
    ]


async def test_create_from_zip_falls_back_to_default_name() -> None:
    projects = _FakeProjects()
    service = _zip_service(_FakeDocuments(), projects)

    await service.create_from_zip(".zip", _zip({"a.pdf": b"x"}))

    assert [p.project_name for p in projects.added] == ["Projekt"]


async def test_create_from_zip_bad_zip_creates_no_project() -> None:
    projects = _FakeProjects()
    service = _zip_service(_FakeDocuments(), projects)

    with pytest.raises(zipfile.BadZipFile):
        await service.create_from_zip("x.zip", b"x")
    assert projects.added == []


async def test_bieter_form_is_enqueued_skipped_others_queued() -> None:
    documents = _FakeDocuments()
    service = _service(documents)
    form = three_field_form()

    created = await service.ingest_documents(
        uuid4(),
        [
            UploadInput("T1.6 FB 331-B Angebotsschreiben.pdf", "application/pdf", form),
            UploadInput("T1.1 FB 312-B Aufforderung.pdf", "application/pdf", form),
            UploadInput("Plan.pdf", "application/pdf", acroform_pdf([])),
        ],
    )

    jobs = service.ingest_jobs
    assert isinstance(jobs, _FakeIngestJobs)
    by_name = {d.file_name: d for d in created}
    bieter = by_name["T1.6 FB 331-B Angebotsschreiben.pdf"]
    assert (bieter.document_type, bieter.form_role, bieter.form_id) == (
        DocumentType.FORM_DOCUMENT,
        FormRole.BIETER,
        "FB 331-B",
    )
    assert jobs.statuses[bieter.document_uuid] is IngestStatus.SKIPPED
    vergabestelle = by_name["T1.1 FB 312-B Aufforderung.pdf"]
    assert vergabestelle.form_role is FormRole.VERGABESTELLE
    assert jobs.statuses[vergabestelle.document_uuid] is IngestStatus.QUEUED
    plan = by_name["Plan.pdf"]
    assert (plan.document_type, plan.form_role) == (DocumentType.PROSE_DOCUMENT, None)
    assert jobs.statuses[plan.document_uuid] is IngestStatus.QUEUED
