"""Enqueue and read a project's Projektinfo jobs for the API."""

from __future__ import annotations

from uuid import UUID

from shared.config import settings
from shared.models.project_info_job import NewProjectInfoJob, ProjectInfoJob
from shared.repositories.project_info_jobs import ProjectInfoJobRepository
from shared.repositories.projects import ProjectRepository


class ProjectInfoJobService:
    def __init__(
        self, projects: ProjectRepository, jobs: ProjectInfoJobRepository
    ) -> None:
        self.projects = projects
        self.jobs = jobs

    async def latest(self, project_uuid: UUID) -> ProjectInfoJob | None:
        return await self.jobs.latest_for_project(project_uuid)

    async def request_run(
        self, project_uuid: UUID, *, overwrite: bool
    ) -> ProjectInfoJob | None:
        """Enqueue a job, or return the project's open one unchanged. None if the
        project does not exist."""
        if await self.projects.get(project_uuid) is None:
            return None
        existing = await self.jobs.open_job(project_uuid)
        if existing is not None:
            return existing
        return await self.jobs.add(
            NewProjectInfoJob(
                project_uuid=project_uuid,
                language=settings.project_info_language,
                overwrite=overwrite,
            )
        )
