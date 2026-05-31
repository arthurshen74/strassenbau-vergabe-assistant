from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.document_thumbnail import NewDocumentThumbnail
from shared.domain.project import NewProject
from shared.domain.project_document import NewProjectDocument
from shared.domain.project_document_type import NewProjectDocumentType
from shared.repositories.document_thumbnails import DocumentThumbnailRepository
from shared.repositories.project_document_types import (
    ProjectDocumentTypeRepository,
)
from shared.repositories.project_documents import ProjectDocumentRepository
from shared.repositories.projects import ProjectRepository


async def _make_document(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            project_id="VS-2026-0042",
            project_name="Autobahn A1 Brückensanierung",
            vergabestelle="Autobahn GmbH des Bundes",
            project_location="Niedersachsen",
        )
    )
    doc_type = await ProjectDocumentTypeRepository(conn).add(
        NewProjectDocumentType(document_type="LV")
    )
    document = await ProjectDocumentRepository(conn).add(
        NewProjectDocument(
            project_uuid=project.project_uuid,
            document_filename="LV_001.pdf",
            document_type_uuid=doc_type.document_type_uuid,
        )
    )
    return document.project_document_uuid


def _new_thumbnail(
    project_document_uuid: UUID, page_number: int
) -> NewDocumentThumbnail:
    return NewDocumentThumbnail(
        project_document_uuid=project_document_uuid,
        page_number=page_number,
        object_key=f"projects/x/raw/y/thumb_{page_number}.webp",
        bucket="roadbuilders",
        width=200,
        height=283,
        content_type="image/webp",
    )


async def test_list_by_document_is_ordered_by_page(conn: AsyncConnection) -> None:
    document_uuid = await _make_document(conn)
    repo = DocumentThumbnailRepository(conn)
    await repo.add(_new_thumbnail(document_uuid, 3))
    await repo.add(_new_thumbnail(document_uuid, 1))
    await repo.add(_new_thumbnail(document_uuid, 2))

    listed = await repo.list_by_document(document_uuid)
    assert [t.page_number for t in listed] == [1, 2, 3]


async def test_unique_page_per_document_blocks_duplicate(
    conn: AsyncConnection,
) -> None:
    document_uuid = await _make_document(conn)
    repo = DocumentThumbnailRepository(conn)
    await repo.add(_new_thumbnail(document_uuid, 1))
    with pytest.raises(IntegrityError):
        await repo.add(_new_thumbnail(document_uuid, 1))


async def test_deleting_document_cascades_to_thumbnails(
    conn: AsyncConnection,
) -> None:
    document_uuid = await _make_document(conn)
    repo = DocumentThumbnailRepository(conn)
    created = await repo.add(_new_thumbnail(document_uuid, 1))

    await ProjectDocumentRepository(conn).delete(document_uuid)

    assert await repo.get(created.thumbnail_uuid) is None
