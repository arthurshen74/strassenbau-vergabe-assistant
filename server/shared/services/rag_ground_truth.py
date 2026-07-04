"""Curation of RAG reference questions: CRUD with ref validation.

Refs (document + page) are validated against the project's ingested documents at the write
boundary — a ref must point at a document of the project, on a page the document has. A question
without refs is legal but flagged on read (refs_missing): it counts only toward answer grading,
not retrieval metrics. The validators are pure so they can be unit-tested without a database.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import Document
from shared.models.rag_ground_truth import (
    NewRagGroundTruth,
    RagGroundTruth,
    RagGroundTruthRead,
    RagGroundTruthUpsert,
    RagRef,
)
from shared.repositories.documents import DocumentRepository
from shared.repositories.rag_ground_truth import RagGroundTruthRepository


def validate_refs(refs: list[RagRef], documents: dict[UUID, Document]) -> list[str]:
    """Boundary validation for the Fundstellen; returns human-readable problems (empty = valid)."""
    problems: list[str] = []
    for ref in refs:
        doc = documents.get(ref.document_uuid)
        if doc is None:
            problems.append(f"Dokument {ref.document_uuid} gehört nicht zum Projekt")
        elif ref.page > doc.number_of_pages:
            problems.append(
                f"Seite {ref.page} liegt außerhalb von {doc.file_name} "
                f"({doc.number_of_pages} Seiten)"
            )
    return problems


def to_read(row: RagGroundTruth) -> RagGroundTruthRead:
    return RagGroundTruthRead(**row.model_dump(), refs_missing=not row.refs)


class RagGroundTruthService:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn
        self._repo = RagGroundTruthRepository(conn)

    async def _validate(self, project_uuid: UUID, payload: RagGroundTruthUpsert) -> None:
        if not payload.refs:
            return
        documents = {
            d.document_uuid: d
            for d in await DocumentRepository(self._conn).list_by_project(project_uuid)
        }
        problems = validate_refs(payload.refs, documents)
        if problems:
            raise ValueError("; ".join(problems))

    async def list(self, project_uuid: UUID) -> list[RagGroundTruthRead]:
        return [to_read(r) for r in await self._repo.list_by_project(project_uuid)]

    async def create(
        self, *, project_uuid: UUID, payload: RagGroundTruthUpsert, user_id: UUID
    ) -> RagGroundTruthRead:
        await self._validate(project_uuid, payload)
        created = await self._repo.add(
            NewRagGroundTruth(
                **payload.model_dump(),
                project_uuid=project_uuid,
                created_by_user_id=user_id,
            )
        )
        return to_read(created)

    async def update(
        self,
        *,
        project_uuid: UUID,
        rag_ground_truth_uuid: UUID,
        payload: RagGroundTruthUpsert,
    ) -> RagGroundTruthRead:
        """Raises LookupError when the question is not in this project."""
        await self._validate(project_uuid, payload)
        updated = await self._repo.update(project_uuid, rag_ground_truth_uuid, payload)
        if updated is None:
            raise LookupError("RAG reference question not found in this project")
        return to_read(updated)

    async def delete(self, project_uuid: UUID, rag_ground_truth_uuid: UUID) -> bool:
        return await self._repo.delete(project_uuid, rag_ground_truth_uuid)
