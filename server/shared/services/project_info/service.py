"""Run one Projektinfo job: fill the project header columns from the tender documents.

For each `ProjectInfoQuery` the latest `RagQueryVersion` in the job's language is run
through hybrid retrieval (`query_text`), the chunks go to one structured synthesis call
(`answer_instruction` sets the value format), and a found value is written to the
query's `projects` column. With `overwrite=false` only NULL columns are filled. A miss
leaves the column untouched. `location` is written as text only; geocoding stays with
the project-context resolver.

Retrieval and the LLM run outside any transaction: the project and the query versions
are read in one unit of work up front and the column updates written in another at the
end.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from shared.clients.llm.client import LLMClient
from shared.config import settings
from shared.models.enums import ProjectInfoQuery
from shared.models.project import Project
from shared.models.project_info_job import ProjectInfoJob, ProjectInfoResult
from shared.models.prompt_version import PromptVersion
from shared.models.rag_query import PROJECT_INFO_TARGET_COLUMN, RagQueryVersion
from shared.services.ingestion.ingestion_service import UnitOfWorkFactory
from shared.services.project_info.llm import resolve_project_info
from shared.services.project_info.queries import PROJECT_INFO_RETRIEVAL_CONFIG
from shared.services.retrieval import RetrievalService

NO_QUERY_VERSION = "no query version"

# Called after each query; the worker refreshes the job's lease with it.
Heartbeat = Callable[[], Awaitable[None]]

# Offline fixtures (settings.calculator_mock): retrieval and the LLM are skipped.
_MOCK_WERTE: dict[ProjectInfoQuery, str] = {
    ProjectInfoQuery.PROJECT_DESCRIPTION: "Deckenerneuerung der L 1172 (mock)",
    ProjectInfoQuery.PROJECT_MASSNAHMENUMMER: "M-2025-0001",
    ProjectInfoQuery.PROJECT_NAME: "L 1172 Deckenerneuerung",
    ProjectInfoQuery.PROJECT_VERGABENUMMER: "VG-2025-0001",
    ProjectInfoQuery.PROJECT_BAULEISTUNG: "Straßenbau",
    ProjectInfoQuery.PROJECT_LOCATION: "Nordhausen",
}


class ProjectInfoService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def run(
        self,
        job: ProjectInfoJob,
        *,
        retrieval: RetrievalService,
        llm: LLMClient,
        prompt: PromptVersion | None,
        heartbeat: Heartbeat,
    ) -> dict[ProjectInfoQuery, ProjectInfoResult]:
        """Resolve every project-info query and write the found values. `prompt` is the
        PROJECT_INFO_RESOLVE PromptVersion (unused in mock)."""
        async with self._uow_factory() as uow:
            project = await uow.projects.get(job.project_uuid)
            queries = {
                key: await uow.rag_queries.get_latest(key, job.language)
                for key in ProjectInfoQuery
            }
        assert project is not None  # the job row cascades with its project

        results: dict[ProjectInfoQuery, ProjectInfoResult] = {}
        changes: dict[str, str] = {}
        for key, query in queries.items():
            if query is None:
                results[key] = ProjectInfoResult(gefunden=False, error=NO_QUERY_VERSION)
                continue
            result = await self._resolve(
                key,
                query,
                job.project_uuid,
                retrieval=retrieval,
                llm=llm,
                prompt=prompt,
            )
            results[key] = result
            await heartbeat()
            column = PROJECT_INFO_TARGET_COLUMN[key]
            if result.gefunden and result.wert and _writable(project, column, job):
                changes[column] = result.wert

        if changes:
            async with self._uow_factory() as uow:
                await uow.projects.update(job.project_uuid, **changes)
        return results

    async def _resolve(
        self,
        key: ProjectInfoQuery,
        query: RagQueryVersion,
        project_uuid: UUID,
        *,
        retrieval: RetrievalService,
        llm: LLMClient,
        prompt: PromptVersion | None,
    ) -> ProjectInfoResult:
        if settings.calculator_mock:
            return ProjectInfoResult(
                gefunden=True,
                wert=_MOCK_WERTE[key],
                konfidenz=1.0,
                beleg="(mock)",
                query_version=query.version,
            )
        assert prompt is not None  # live resolution always carries the prompt
        ctx = await retrieval.retrieve_context(
            query.query_text, project_uuid, PROJECT_INFO_RETRIEVAL_CONFIG
        )
        snippets = [c.chunk_text for c in ctx.context]
        ext, _summary = await resolve_project_info(
            llm, query, snippets, prompt=prompt, project_uuid=project_uuid
        )
        return ProjectInfoResult(
            gefunden=ext.gefunden,
            wert=ext.wert,
            konfidenz=ext.konfidenz,
            beleg=ext.beleg,
            query_version=query.version,
        )


def _writable(project: Project, column: str, job: ProjectInfoJob) -> bool:
    return job.overwrite or getattr(project, column) is None
