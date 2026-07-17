from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.nlp import DocumentLayout, LayoutRegion
from shared.models.project import NewProject
from shared.repositories.document_layout_regions import DocumentLayoutRegionRepository
from shared.repositories.documents import DocumentRepository
from shared.repositories.projects import ProjectRepository


async def _document(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-DLR",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name="bb.pdf",
            number_of_pages=3,
        )
    )
    return doc.document_uuid


def _layout(document_uuid: UUID, model_version: str) -> DocumentLayout:
    return DocumentLayout(
        document_uuid=document_uuid,
        model_version=model_version,
        regions=[
            LayoutRegion(page=1, label="page_header", bbox=(10.0, 40.0, 200.0, 60.0)),
            LayoutRegion(page=2, label="text", bbox=(70.0, 100.0, 500.0, 300.0)),
        ],
    )


async def test_put_get_roundtrip(conn: AsyncConnection) -> None:
    document_uuid = await _document(conn)
    repo = DocumentLayoutRegionRepository(conn)

    await repo.put(_layout(document_uuid, "2.99.0"))
    layout = await repo.get(document_uuid, "2.99.0")

    assert layout is not None
    assert layout.model_version == "2.99.0"
    assert [r.label for r in layout.regions] == ["page_header", "text"]
    assert layout.regions[0].bbox == (10.0, 40.0, 200.0, 60.0)


async def test_model_version_mismatch_is_a_miss(conn: AsyncConnection) -> None:
    document_uuid = await _document(conn)
    repo = DocumentLayoutRegionRepository(conn)

    await repo.put(_layout(document_uuid, "2.99.0"))

    assert await repo.get(document_uuid, "3.0.0") is None


async def test_concurrent_put_is_first_writer_wins(conn: AsyncConnection) -> None:
    document_uuid = await _document(conn)
    repo = DocumentLayoutRegionRepository(conn)

    await repo.put(_layout(document_uuid, "2.99.0"))
    second = _layout(document_uuid, "2.99.0")
    second.regions = second.regions[:1]
    await repo.put(second)

    layout = await repo.get(document_uuid, "2.99.0")
    assert layout is not None
    assert len(layout.regions) == 2
