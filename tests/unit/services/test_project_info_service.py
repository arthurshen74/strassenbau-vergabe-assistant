from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from shared.config import settings
from shared.models.enums import IngestStatus, ProjectInfoQuery, PromptType
from shared.models.project import Project
from shared.models.project_info_job import ProjectInfoJob, ProjectInfoResult
from shared.models.prompt_version import PromptVersion
from shared.models.rag_query import RagQueryVersion
from shared.services.project_info.llm import ProjektInfoAufloesung
from shared.services.project_info.service import NO_QUERY_VERSION, ProjectInfoService

_NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def _project(**fields: Any) -> Project:
    base: dict[str, Any] = {
        "project_uuid": uuid4(),
        "project_name": "tender",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    return Project(**{**base, **fields})


def _job(project_uuid: UUID, *, overwrite: bool) -> ProjectInfoJob:
    return ProjectInfoJob(
        job_uuid=uuid4(),
        project_uuid=project_uuid,
        language="de",
        overwrite=overwrite,
        status=IngestStatus.RUNNING,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _query(key: ProjectInfoQuery, version: int = 1) -> RagQueryVersion:
    return RagQueryVersion(
        rag_query_version_uuid=uuid4(),
        query_key=key,
        language="de",
        version=version,
        name=key.value,
        description=f"desc {key.value}",
        query_text=f"retrieve {key.value}",
        answer_instruction=f"answer {key.value}",
        created_at=_NOW,
    )


def _prompt() -> PromptVersion:
    return PromptVersion(
        prompt_version_uuid=uuid4(),
        prompt_type=PromptType.PROJECT_INFO_RESOLVE,
        version=1,
        model_name="openai/gpt-5.4",
        system_prompt="Du ermittelst ein Projektfeld.",
        created_at=_NOW,
    )


class _FakeProjects:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.updates: list[dict[str, str]] = []

    async def get(self, project_uuid: UUID) -> Project | None:
        return self.project

    async def update(self, project_uuid: UUID, **changes: str) -> Project:
        self.updates.append(changes)
        return self.project


class _FakeRagQueries:
    def __init__(self, queries: dict[ProjectInfoQuery, RagQueryVersion]) -> None:
        self.queries = queries

    async def get_latest(self, key: ProjectInfoQuery, language: str) -> RagQueryVersion | None:
        return self.queries.get(key)


def _factory(projects: _FakeProjects, rag_queries: _FakeRagQueries):
    @asynccontextmanager
    async def factory():
        yield SimpleNamespace(projects=projects, rag_queries=rag_queries)

    return factory


class _FakeRetrieval:
    def __init__(self) -> None:
        self.questions: list[str] = []

    async def retrieve_context(self, question: str, project_uuid: UUID, config: Any) -> Any:
        self.questions.append(question)
        return SimpleNamespace(context=[SimpleNamespace(chunk_text=f"chunk for {question}")])


class _FakeLLM:
    """Answers per query name; a name missing from `answers` is not found."""

    def __init__(self, answers: dict[ProjectInfoQuery, str]) -> None:
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    async def chat_with_reasoning(self, **kwargs: Any) -> tuple[ProjektInfoAufloesung, None]:
        self.calls.append(kwargs)
        user = kwargs["messages"][1]["content"]
        for key, wert in self.answers.items():
            if f'"name": "{key.value}"' in user:
                return ProjektInfoAufloesung(gefunden=True, wert=wert, konfidenz=0.9, beleg=wert), None
        return ProjektInfoAufloesung(gefunden=False, konfidenz=0.1), None


async def _no_heartbeat() -> None:
    pass


async def _run(
    project: Project,
    *,
    overwrite: bool,
    answers: dict[ProjectInfoQuery, str],
    queries: dict[ProjectInfoQuery, RagQueryVersion] | None = None,
) -> tuple[dict[ProjectInfoQuery, ProjectInfoResult], _FakeProjects, _FakeRetrieval, _FakeLLM]:
    projects = _FakeProjects(project)
    if queries is None:
        queries = {key: _query(key) for key in ProjectInfoQuery}
    retrieval = _FakeRetrieval()
    llm = _FakeLLM(answers)
    result = await ProjectInfoService(_factory(projects, _FakeRagQueries(queries))).run(
        _job(project.project_uuid, overwrite=overwrite),
        retrieval=retrieval,  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        prompt=_prompt(),
        heartbeat=_no_heartbeat,
    )
    return result, projects, retrieval, llm


@pytest.fixture(autouse=True)
def _live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)


async def test_found_values_written_to_target_columns() -> None:
    answers = {
        ProjectInfoQuery.PROJECT_VERGABENUMMER: "VG-7",
        ProjectInfoQuery.PROJECT_NAME: "B 247 OD Mühlhausen",
    }
    result, projects, retrieval, llm = await _run(_project(), overwrite=True, answers=answers)

    assert projects.updates == [{"vergabe_id": "VG-7", "project_name": "B 247 OD Mühlhausen"}]
    assert len(retrieval.questions) == len(ProjectInfoQuery)
    assert retrieval.questions[0].startswith("retrieve ")  # query_text drives retrieval
    user = llm.calls[0]["messages"][1]["content"]
    assert "answer_instruction" in user and "retrieve " not in user.split("Auszüge")[0]


async def test_not_found_leaves_column() -> None:
    result, projects, _r, _l = await _run(_project(), overwrite=True, answers={})
    assert projects.updates == []
    assert all(not r.gefunden for r in result.values())


async def test_missing_query_version_recorded() -> None:
    queries = {ProjectInfoQuery.PROJECT_NAME: _query(ProjectInfoQuery.PROJECT_NAME)}
    result, _p, retrieval, _l = await _run(
        _project(),
        overwrite=True,
        answers={ProjectInfoQuery.PROJECT_NAME: "X"},
        queries=queries,
    )
    assert retrieval.questions == ["retrieve project-name"]
    assert result[ProjectInfoQuery.PROJECT_BAULEISTUNG] == ProjectInfoResult(
        gefunden=False, error=NO_QUERY_VERSION
    )


async def test_without_overwrite_only_null_columns_filled() -> None:
    project = _project(vergabe_id="VG-manual")
    answers = {
        ProjectInfoQuery.PROJECT_VERGABENUMMER: "VG-7",
        ProjectInfoQuery.PROJECT_BAULEISTUNG: "Straßenbau",
    }
    result, projects, _r, _l = await _run(project, overwrite=False, answers=answers)
    assert projects.updates == [{"bauleistung": "Straßenbau"}]
    # The skipped value is still reported.
    assert result[ProjectInfoQuery.PROJECT_VERGABENUMMER].wert == "VG-7"


async def test_result_shape() -> None:
    queries = {key: _query(key, version=3) for key in ProjectInfoQuery}
    result, _p, _r, _l = await _run(
        _project(),
        overwrite=True,
        answers={ProjectInfoQuery.PROJECT_LOCATION: "Erfurt"},
        queries=queries,
    )
    assert set(result) == set(ProjectInfoQuery)
    assert result[ProjectInfoQuery.PROJECT_LOCATION].model_dump(mode="json") == {
        "gefunden": True,
        "wert": "Erfurt",
        "konfidenz": 0.9,
        "beleg": "Erfurt",
        "query_version": 3,
        "error": None,
    }


async def test_heartbeat_after_every_query() -> None:
    beats: list[None] = []

    async def heartbeat() -> None:
        beats.append(None)

    projects = _FakeProjects(_project())
    queries = {key: _query(key) for key in ProjectInfoQuery}
    await ProjectInfoService(_factory(projects, _FakeRagQueries(queries))).run(
        _job(projects.project.project_uuid, overwrite=True),
        retrieval=_FakeRetrieval(),  # type: ignore[arg-type]
        llm=_FakeLLM({}),  # type: ignore[arg-type]
        prompt=_prompt(),
        heartbeat=heartbeat,
    )
    assert len(beats) == len(ProjectInfoQuery)
