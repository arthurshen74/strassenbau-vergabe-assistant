"""CRUD round-trip for the rag_ground_truth repository, including project scoping."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import RagQuestionCategory, RagQuestionType
from shared.models.project import NewProject
from shared.models.rag_ground_truth import (
    NewRagGroundTruth,
    RagGroundTruthUpsert,
    RagRef,
)
from shared.repositories.projects import ProjectRepository
from shared.repositories.rag_ground_truth import RagGroundTruthRepository

USER = UUID("00000000-0000-0000-0000-000000000001")


async def _project(conn: AsyncConnection, vergabe_id: str) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id=vergabe_id,
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    return project.project_uuid


def _new(project_uuid: UUID, refs: list[RagRef] | None = None) -> NewRagGroundTruth:
    return NewRagGroundTruth(
        project_uuid=project_uuid,
        question="Welche Bindefrist gilt für das Angebot?",
        gold_answer="bis 28.08.2026",
        refs=refs or [],
        question_type=RagQuestionType.LOOKUP,
        category=RagQuestionCategory.KALKULATOR,
        created_by_user_id=USER,
    )


async def test_add_get_list_roundtrip(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn, "VG-RAG-1")
    repo = RagGroundTruthRepository(conn)
    refs = [RagRef(document_uuid=uuid4(), page=14)]

    created = await repo.add(_new(project_uuid, refs))
    assert created.refs == refs

    fetched = await repo.get(project_uuid, created.rag_ground_truth_uuid)
    assert fetched is not None
    assert fetched.question == created.question
    assert fetched.refs == refs

    assert len(await repo.list_by_project(project_uuid)) == 1
    # Scoped get: another project's uuid does not resolve the row.
    assert await repo.get(uuid4(), created.rag_ground_truth_uuid) is None


async def test_update_replaces_content_and_scopes(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn, "VG-RAG-2")
    repo = RagGroundTruthRepository(conn)
    created = await repo.add(_new(project_uuid))

    payload = RagGroundTruthUpsert(
        question="Welche Vertragsstrafe ist vereinbart?",
        gold_answer="0,2 % je Werktag, max. 5 %",
        refs=[RagRef(document_uuid=uuid4(), page=3)],
        question_type=RagQuestionType.CONSTRAINT_SURFACING,
        category=RagQuestionCategory.BAULEITER,
    )
    updated = await repo.update(project_uuid, created.rag_ground_truth_uuid, payload)
    assert updated is not None
    assert updated.question == payload.question
    assert updated.question_type == RagQuestionType.CONSTRAINT_SURFACING
    assert updated.created_by_user_id == USER

    assert await repo.update(uuid4(), created.rag_ground_truth_uuid, payload) is None


async def test_delete(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn, "VG-RAG-3")
    repo = RagGroundTruthRepository(conn)
    created = await repo.add(_new(project_uuid))

    assert await repo.delete(uuid4(), created.rag_ground_truth_uuid) is False
    assert await repo.delete(project_uuid, created.rag_ground_truth_uuid) is True
    assert await repo.get(project_uuid, created.rag_ground_truth_uuid) is None
