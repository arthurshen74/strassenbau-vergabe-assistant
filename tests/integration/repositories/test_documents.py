from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

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


async def test_get_lv_document(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "prose.pdf"))
    lv = await repo.add(_doc(pid, DocumentType.LV_DOCUMENT, "lv.pdf"))
    found = await repo.get_lv_document(pid)
    assert found is not None
    assert found.document_uuid == lv.document_uuid
    assert found.document_type == DocumentType.LV_DOCUMENT


async def test_get_lv_document_none_when_absent(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "prose.pdf"))
    assert await repo.get_lv_document(pid) is None


async def test_second_lv_document_raises(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    await repo.add(_doc(pid, DocumentType.LV_DOCUMENT, "lv1.pdf"))
    with pytest.raises(IntegrityError):
        await repo.add(_doc(pid, DocumentType.LV_DOCUMENT, "lv2.pdf"))


async def test_delete_removes(conn: AsyncConnection) -> None:
    repo = DocumentRepository(conn)
    pid = await _project(conn)
    created = await repo.add(_doc(pid, DocumentType.PROSE_DOCUMENT, "p.pdf"))
    await repo.delete(created.document_uuid)
    assert await repo.get(created.document_uuid) is None
