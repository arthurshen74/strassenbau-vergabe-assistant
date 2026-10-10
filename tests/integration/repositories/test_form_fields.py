from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import NewDocument
from shared.models.enums import DocumentType, FormRole
from shared.models.form_field import NewFormField
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.form_fields import FormFieldRepository
from shared.repositories.projects import ProjectRepository


async def _form_document(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(NewProject(project_name="P"))
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.FORM_DOCUMENT,
            file_name="T1.1 FB 312-B.pdf",
            number_of_pages=1,
            form_role=FormRole.VERGABESTELLE,
            form_id="FB 312-B",
        )
    )
    assert (doc.form_role, doc.form_id) == (FormRole.VERGABESTELLE, "FB 312-B")
    return doc.document_uuid


def _field(document_uuid: UUID, order: int, name: str, value: str) -> NewFormField:
    return NewFormField(
        document_uuid=document_uuid,
        field_order=order,
        section="Kopf",
        name=name,
        label=None if order else "Vergabenummer",
        value=value,
        page=1,
    )


async def test_add_list_delete_round_trip(conn: AsyncConnection) -> None:
    repo = FormFieldRepository(conn)
    doc = await _form_document(conn)
    await repo.add_many([_field(doc, 1, "Ort", "Berlin"), _field(doc, 0, "VNR", "26/001")])

    listed = await repo.list_for_document(doc)
    assert [(f.field_order, f.name, f.label, f.value) for f in listed] == [
        (0, "VNR", "Vergabenummer", "26/001"),
        (1, "Ort", None, "Berlin"),
    ]

    assert await repo.delete_for_document(doc) == 2
    assert await repo.list_for_document(doc) == []


async def test_add_many_empty_returns_empty(conn: AsyncConnection) -> None:
    assert await FormFieldRepository(conn).add_many([]) == []


async def test_form_document_requires_a_role(conn: AsyncConnection) -> None:
    project = await ProjectRepository(conn).add(NewProject(project_name="P"))
    with pytest.raises(IntegrityError):
        await DocumentRepository(conn).add(
            NewDocument(
                project_uuid=project.project_uuid,
                document_type=DocumentType.FORM_DOCUMENT,
                file_name="f.pdf",
                number_of_pages=1,
            )
        )


async def test_prose_document_rejects_a_role(conn: AsyncConnection) -> None:
    project = await ProjectRepository(conn).add(NewProject(project_name="P"))
    with pytest.raises(IntegrityError):
        await DocumentRepository(conn).add(
            NewDocument(
                project_uuid=project.project_uuid,
                document_type=DocumentType.PROSE_DOCUMENT,
                file_name="p.pdf",
                number_of_pages=1,
                form_role=FormRole.BIETER,
            )
        )
