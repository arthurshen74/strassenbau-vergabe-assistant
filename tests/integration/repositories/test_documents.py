from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.documents import documents
from shared.models.document import NewDocument
from shared.models.enums import DocumentType
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.projects import ProjectRepository


async def _project(conn: AsyncConnection) -> object:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-DOC",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    return project.project_uuid


def _doc(project_uuid: object, document_type: DocumentType, file_name: str) -> NewDocument:
    return NewDocument(
        project_uuid=project_uuid,
        document_type=document_type,
        file_name=file_name,
        number_of_pages=1,
    )


async def test_add_and_get(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    created = await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "p.pdf"))
    fetched = await repo.get(created.document_uuid)
    assert fetched is not None
    assert fetched.document_type == DocumentType.PROSE_DOCUMENT
    assert fetched.file_name == "p.pdf"


async def test_list_by_project(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    await repo.add(_doc(pid, DocumentType.LV_DOCUMENT, "lv.pdf"))
    await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "a.pdf"))
    await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "b.pdf"))
    listed = await repo.list_by_project(pid)
    assert {d.file_name for d in listed} == {"lv.pdf", "a.pdf", "b.pdf"}


async def _set_created_at(
    conn: AsyncConnection, document_uuid: UUID, created_at: datetime
) -> None:
    await conn.execute(
        update(documents)
        .where(documents.c.document_uuid == document_uuid)
        .values(created_at=created_at)
    )


async def test_two_lv_documents_in_one_project(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    await repo.add(_doc(pid, DocumentType.LV_DOCUMENT, "lv.x83"))
    await repo.add(_doc(pid, DocumentType.LV_DOCUMENT, "lv.d83"))
    listed = await repo.list_lv_documents(pid)
    assert {d.file_name for d in listed} == {"lv.x83", "lv.d83"}


async def test_list_lv_documents_oldest_first_without_prose(
    conn: AsyncConnection,
) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    newer = await repo.add(_doc(pid, DocumentType.LV_DOCUMENT, "los2.d83"))
    await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "prose.pdf"))
    older = await repo.add(_doc(pid, DocumentType.LV_DOCUMENT, "los1.x83"))
    base = datetime(2026, 1, 1, tzinfo=UTC)
    await _set_created_at(conn, older.document_uuid, base)
    await _set_created_at(conn, newer.document_uuid, base + timedelta(minutes=1))

    listed = await repo.list_lv_documents(pid)

    assert [d.file_name for d in listed] == ["los1.x83", "los2.d83"]


async def test_list_lv_documents_empty_when_absent(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "prose.pdf"))
    assert await repo.list_lv_documents(pid) == []


async def test_delete_removes(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    created = await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "p.pdf"))
    await repo.delete(created.document_uuid)
    assert await repo.get(created.document_uuid) is None
