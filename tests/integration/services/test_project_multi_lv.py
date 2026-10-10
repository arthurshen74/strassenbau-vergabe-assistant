"""Several LV documents in one project: uploads add, deletes stay per document."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import DocumentType, LVTextKind
from shared.models.lv_item import NewLVItem
from shared.models.lv_text import NewLVText
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.lv_texts import LVTextRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.thumbnails import ThumbnailRepository
from shared.services.project_service import ProjectService, UploadInput


class _FakeStorage:
    def __init__(self) -> None:
        self.deleted_keys: list[str] = []

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        pass

    def delete_objects(self, keys: list[str]) -> None:
        self.deleted_keys.extend(keys)


class _FakeSearch:
    def __init__(self) -> None:
        self.archived: list[tuple[UUID, list[UUID]]] = []

    async def archive_and_delete_document(
        self, project_uuid: UUID, document_uuid: UUID, lv_source_uuids: list[UUID]
    ) -> int:
        self.archived.append((document_uuid, lv_source_uuids))
        return 0


def _service(
    conn: AsyncConnection, storage: _FakeStorage, search: _FakeSearch
) -> ProjectService:
    return ProjectService(
        ProjectRepository(conn),
        DocumentRepository(conn),
        IngestJobRepository(conn),
        storage=storage,  # type: ignore[arg-type]
        thumbnails=ThumbnailRepository(conn),
        lv_items=LVItemRepository(conn),
        search=search,  # type: ignore[arg-type]
        lv_texts=LVTextRepository(conn),
    )


def _item(document_uuid: UUID, oz: str) -> NewLVItem:
    return NewLVItem(
        document_uuid=document_uuid,
        oz=oz,
        kurztext="k",
        langtext="l",
        menge=Decimal("1"),
        einheit="m",
    )


def _text(document_uuid: UUID) -> NewLVText:
    return NewLVText(
        document_uuid=document_uuid,
        kind=LVTextKind.REMARK,
        index=0,
        sequence=0,
        body="h",
    )


async def test_two_gaeb_uploads_then_delete_one_keeps_the_other(
    conn: AsyncConnection,
) -> None:
    project = await ProjectRepository(conn).add(NewProject(project_name="Multi-LV"))
    storage, search = _FakeStorage(), _FakeSearch()
    service = _service(conn, storage, search)

    first = await service.ingest_documents(
        project.project_uuid, [UploadInput("Los1.x83", "application/xml", b"<a/>")]
    )
    second = await service.ingest_documents(
        project.project_uuid, [UploadInput("Los2.d83", "text/plain", b"00")]
    )
    los1, los2 = first[0].document_uuid, second[0].document_uuid
    lv_documents = await DocumentRepository(conn).list_lv_documents(
        project.project_uuid
    )
    assert {d.document_uuid for d in lv_documents} == {los1, los2}
    assert all(d.document_type == DocumentType.LV_DOCUMENT for d in lv_documents)

    items = LVItemRepository(conn)
    texts = LVTextRepository(conn)
    [los1_item] = await items.add_many([_item(los1, "01.0010")])
    await items.add_many([_item(los2, "01.0010")])
    [los1_text], _ = await texts.replace(los1, [_text(los1)])
    await texts.replace(los2, [_text(los2)])

    assert await service.delete_document(project.project_uuid, los1)

    # Only the deleted document's footprint is handed to ES; the other LV survives.
    assert search.archived == [(los1, [los1_item.lv_item_uuid, los1_text.lv_text_uuid])]
    remaining = await DocumentRepository(conn).list_lv_documents(project.project_uuid)
    assert [d.document_uuid for d in remaining] == [los2]
    assert [
        i.document_uuid for i in await items.list_by_project(project.project_uuid)
    ] == [los2]
    assert [
        t.document_uuid for t in await texts.list_by_project(project.project_uuid)
    ] == [los2]
