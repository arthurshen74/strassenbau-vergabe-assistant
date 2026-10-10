from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.project import NewProject
from shared.models.source_line import NewSourceLine
from shared.repositories.documents import DocumentRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.source_lines import SourceLineRepository


async def _document(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-SL",
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
            number_of_pages=1,
        )
    )
    return doc.document_uuid


def _line(document_uuid: UUID, line_id: int, text: str) -> NewSourceLine:
    return NewSourceLine(
        document_uuid=document_uuid,
        line_id=line_id,
        page=1,
        bbox=(0.0, float(line_id), 1.0, float(line_id) + 1.0),
        line_text=text,
    )


async def test_add_many_and_list_ordered(conn: AsyncConnection) -> None:
    repo = SourceLineRepository(conn)
    doc = await _document(conn)
    # Inserted out of order; list_by_document must come back ordered by line_id.
    await repo.add_many([_line(doc, 3, "c"), _line(doc, 1, "a"), _line(doc, 2, "b")])
    listed = await repo.list_by_document(doc)
    assert [line.line_id for line in listed] == [1, 2, 3]
    assert [line.line_text for line in listed] == ["a", "b", "c"]
    assert listed[0].bbox == (0.0, 1.0, 1.0, 2.0)


async def test_add_many_empty_returns_empty(conn: AsyncConnection) -> None:
    repo = SourceLineRepository(conn)
    assert await repo.add_many([]) == []


async def test_add_many_upserts_on_natural_key(conn: AsyncConnection) -> None:
    repo = SourceLineRepository(conn)
    doc = await _document(conn)
    await repo.add_many([_line(doc, 1, "a"), _line(doc, 2, "b")])
    # Re-ingestion replays: line 2 changes, line 3 is new. No duplicate key error.
    await repo.add_many([_line(doc, 2, "b-updated"), _line(doc, 3, "c")])
    listed = await repo.list_by_document(doc)
    assert [line.line_id for line in listed] == [1, 2, 3]
    by_id = {line.line_id: line.line_text for line in listed}
    assert by_id[2] == "b-updated"


async def test_add_many_exceeds_bind_parameter_limit(conn: AsyncConnection) -> None:
    repo = SourceLineRepository(conn)
    doc = await _document(conn)
    # 7000 rows x 5 bound columns is past asyncpg's 32767 parameter cap.
    added = await repo.add_many([_line(doc, i, f"l{i}") for i in range(7000)])
    assert len(added) == 7000
    assert len(await repo.list_by_document(doc)) == 7000
