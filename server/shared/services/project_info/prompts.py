"""Load the project-info resolution prompt."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import PromptType
from shared.models.prompt_version import PromptVersion
from shared.repositories.prompt_versions import PromptVersionRepository


class ProjectInfoPromptNotSeededError(Exception):
    """PROJECT_INFO_RESOLVE has no version in prompt_versions (run
    scripts.seed.prompts)."""


async def load_project_info_prompt(conn: AsyncConnection) -> PromptVersion:
    pv = await PromptVersionRepository(conn).get_latest(PromptType.PROJECT_INFO_RESOLVE)
    if pv is None:
        raise ProjectInfoPromptNotSeededError(
            "no prompt version for project_info_resolve; run `python -m "
            "scripts.seed.prompts`"
        )
    return pv
