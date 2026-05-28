from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.domain.project import NewProject
from shared.domain.project_document import NewProjectDocument
from shared.domain.project_document_type import NewProjectDocumentType
from shared.repositories.project_document_types import (
    ProjectDocumentTypeRepository,
)
from shared.repositories.project_documents import ProjectDocumentRepository
from shared.repositories.projects import ProjectRepository


async def _make_project(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            project_id="VS-2026-0042",
            project_name="Autobahn A1 Brückensanierung",
            vergabe_stelle="Autobahn GmbH des Bundes",
            project_location="Niedersachsen",
        )
    )
    return project.project_uuid


async def _make_document_type(conn: AsyncConnection, document_type: str) -> UUID:
    doc_type = await ProjectDocumentTypeRepository(conn).add(
        NewProjectDocumentType(document_type=document_type)
    )
    return doc_type.document_type_uuid


def _new_document(project_uuid: UUID, document_type_uuid: UUID) -> NewProjectDocument:
    return NewProjectDocument(
        project_uuid=project_uuid,
        document_filename="LV_001.pdf",
        document_type_uuid=document_type_uuid,
        number_of_pages=12,
    )


async def test_add_round_trips_and_sets_ingested_at(conn: AsyncConnection) -> None:
    project_uuid = await _make_project(conn)
    type_uuid = await _make_document_type(conn, "LV")
    repo = ProjectDocumentRepository(conn)

    created = await repo.add(_new_document(project_uuid, type_uuid))

    assert created.project_document_uuid is not None
    assert created.project_uuid == project_uuid
    assert created.document_type_uuid == type_uuid
    assert created.ingested_at is not None


async def test_list_by_project_returns_only_that_projects_docs(
    conn: AsyncConnection,
) -> None:
    project_uuid = await _make_project(conn)
    type_uuid = await _make_document_type(conn, "LV")
    repo = ProjectDocumentRepository(conn)
    a = await repo.add(_new_document(project_uuid, type_uuid))

    listed = await repo.list_by_project(project_uuid)
    assert {d.project_document_uuid for d in listed} == {a.project_document_uuid}


async def test_deleting_project_cascades_to_documents(
    conn: AsyncConnection,
) -> None:
    project_uuid = await _make_project(conn)
    type_uuid = await _make_document_type(conn, "LV")
    repo = ProjectDocumentRepository(conn)
    created = await repo.add(_new_document(project_uuid, type_uuid))

    await ProjectRepository(conn).delete(project_uuid)

    assert await repo.get(created.project_document_uuid) is None


async def test_deleting_referenced_document_type_is_restricted(
    conn: AsyncConnection,
) -> None:
    project_uuid = await _make_project(conn)
    type_uuid = await _make_document_type(conn, "LV")
    await ProjectDocumentRepository(conn).add(
        _new_document(project_uuid, type_uuid)
    )

    with pytest.raises(IntegrityError):
        await ProjectDocumentTypeRepository(conn).delete(type_uuid)
