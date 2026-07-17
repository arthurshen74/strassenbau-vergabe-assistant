"""Business logic for prompt versions.

PromptVersions are immutable and append-only: each create appends the next version for
its prompt_type (the repository assigns the number). The service translates between the
API DTOs and the repository's domain create-model.
"""

from __future__ import annotations

from shared.models.enums import PromptType
from shared.models.prompt_version import NewPromptVersion
from shared.models.prompt_version_schema import PromptVersionCreate, PromptVersionRead
from shared.repositories.prompt_versions import PromptVersionRepository


class PromptService:
    def __init__(self, prompt_versions: PromptVersionRepository) -> None:
        self.prompt_versions = prompt_versions

    async def list_versions(self, prompt_type: PromptType) -> list[PromptVersionRead]:
        versions = await self.prompt_versions.list_by_type(prompt_type)
        return [PromptVersionRead.model_validate(v) for v in versions]

    async def list_latest(self) -> list[PromptVersionRead]:
        """Latest version of every prompt type that has one (skips unseeded types)."""
        latest: list[PromptVersionRead] = []
        for prompt_type in PromptType:
            found = await self.prompt_versions.get_latest(prompt_type)
            if found is not None:
                latest.append(PromptVersionRead.model_validate(found))
        return latest

    async def get_version(
        self, prompt_type: PromptType, version: int
    ) -> PromptVersionRead | None:
        found = await self.prompt_versions.get_by_type_and_version(prompt_type, version)
        return PromptVersionRead.model_validate(found) if found else None

    async def get_latest(self, prompt_type: PromptType) -> PromptVersionRead | None:
        found = await self.prompt_versions.get_latest(prompt_type)
        return PromptVersionRead.model_validate(found) if found else None

    async def create_version(self, payload: PromptVersionCreate) -> PromptVersionRead:
        created = await self.prompt_versions.add(
            NewPromptVersion(**payload.model_dump())
        )
        return PromptVersionRead.model_validate(created)
