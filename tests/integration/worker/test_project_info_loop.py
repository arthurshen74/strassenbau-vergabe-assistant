from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from scripts.seed.rag_queries import load_rag_query_versions
from shared.config import settings
from shared.db.unit_of_work import UnitOfWork
from shared.models.document import NewDocument
from shared.models.enums import DocumentType, IngestStatus, ProjectInfoQuery
from shared.models.ingest_job import NewIngestJob
from shared.models.project import NewProject
from shared.models.project_info_job import NewProjectInfoJob
from shared.repositories.documents import DocumentRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.project_info_activity import ProjectInfoActivityLogRepository
from shared.repositories.project_info_jobs import ProjectInfoJobRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.rag_queries import RagQueryVersionRepository
from shared.services.project_info.progress import ProjectInfoPhase
from shared.services.project_info.service import _MOCK_WERTE
from worker.project_info_loop import process_one_project_info


def _factory(conn: AsyncConnection):
    @asynccontextmanager
    async def factory() -> AsyncIterator[UnitOfWork]:
        yield UnitOfWork(conn)

    return factory


def _kwargs() -> dict[str, Any]:
    # Mock mode never touches the clients.
    return {
        "worker_id": "test-worker",
        "engine": None,
        "llm": None,
        "embeddings": None,
        "search": None,
        "reranker": None,
    }


async def test_project_info_job_runs_after_ingest_and_fills_project(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "calculator_mock", True)
    rag_queries = RagQueryVersionRepository(conn)
    for new in load_rag_query_versions():
        await rag_queries.add(new)
    project = await ProjectRepository(conn).add(NewProject(project_name="tender"))
    doc = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.PROSE_DOCUMENT,
            file_name="p.pdf",
            number_of_pages=1,
        )
    )
    await IngestJobRepository(conn).add(
        NewIngestJob(document_uuid=doc.document_uuid, status=IngestStatus.DONE)
    )
    job = await ProjectInfoJobRepository(conn).add(
        NewProjectInfoJob(project_uuid=project.project_uuid, language="de", overwrite=True)
    )

    ran = await process_one_project_info(_factory(conn), **_kwargs())  # type: ignore[arg-type]

    assert ran is True
    finished = await ProjectInfoJobRepository(conn).get(job.job_uuid)
    assert finished is not None
    assert finished.status == IngestStatus.DONE, finished.error
    assert finished.result is not None
    assert all(r.gefunden for r in finished.result.values())
    updated = await ProjectRepository(conn).get(project.project_uuid)
    assert updated is not None
    assert updated.project_name == _MOCK_WERTE[ProjectInfoQuery.PROJECT_NAME]
    assert updated.vergabe_id == _MOCK_WERTE[ProjectInfoQuery.PROJECT_VERGABENUMMER]
    assert updated.location == _MOCK_WERTE[ProjectInfoQuery.PROJECT_LOCATION]

    lines = await ProjectInfoActivityLogRepository(conn).tail(job.job_uuid, 0, 500)
    assert {line.phase for line in lines} == set(ProjectInfoPhase)
    assert lines[0].message.startswith("claimed (attempt 1) by test-worker")
    assert lines[-1].message.startswith("done in ")
    assert lines[-1].message.endswith(f"{len(ProjectInfoQuery)} of {len(ProjectInfoQuery)} found")
    assert all(line.worker_id == "test-worker" for line in lines)


async def test_project_info_empty_queue_returns_false(conn: AsyncConnection) -> None:
    ran = await process_one_project_info(_factory(conn), **_kwargs())  # type: ignore[arg-type]
    assert ran is False
