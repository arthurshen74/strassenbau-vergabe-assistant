from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.project import NewProject
from shared.models.thumbnail import NewThumbnail
from shared.repositories.documents import DocumentRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.thumbnails import ThumbnailRepository


async def _document(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-TN",
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
            number_of_pages=3,
        )
    )
    return doc.document_uuid


def _thumb(document_uuid: UUID, page_number: int) -> NewThumbnail:
    return NewThumbnail(
        document_uuid=document_uuid,
        page_number=page_number,
        object_key=f"thumbs/{document_uuid}/{page_number}.png",
        bucket="roadbuilders",
        width=200,
        height=280,
        content_type="image/png",
    )


async def test_add_and_list_ordered_by_page(conn: AsyncConnection) -> None:
    repo = ThumbnailRepository(conn)
    doc = await _document(conn)
    await repo.add(_thumb(doc, 3))
    await repo.add(_thumb(doc, 1))
    await repo.add(_thumb(doc, 2))
    listed = await repo.list_by_document(doc)
    assert [t.page_number for t in listed] == [1, 2, 3]
    assert listed[0].object_key.endswith("1.png")


async def test_add_returns_persisted_row(conn: AsyncConnection) -> None:
    repo = ThumbnailRepository(conn)
    doc = await _document(conn)
    created = await repo.add(_thumb(doc, 1))
    assert created.thumbnail_uuid is not None
    assert created.content_type == "image/png"


async def test_add_many_upserts_on_document_and_page(conn: AsyncConnection) -> None:
    repo = ThumbnailRepository(conn)
    doc = await _document(conn)
    first = await repo.add_many([_thumb(doc, 1), _thumb(doc, 2)])

    # Re-ingest page 1 with new dimensions/key: it updates in place, keeping the uuid.
    again = await repo.add_many(
        [
            NewThumbnail(
                document_uuid=doc,
                page_number=1,
                object_key=f"thumbs/{doc}/1.jpg",
                bucket="roadbuilders",
                width=400,
                height=560,
                content_type="image/jpeg",
            )
        ]
    )

    by_page = {t.page_number: t for t in first}
    assert again[0].thumbnail_uuid == by_page[1].thumbnail_uuid
    rows = await repo.list_by_document(doc)
    assert [r.page_number for r in rows] == [1, 2]  # still two rows, not three
    assert rows[0].content_type == "image/jpeg" and rows[0].width == 400
