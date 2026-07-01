"""Load the project-context resolution prompt, independently of the per-position calc prompts.

Kept separate from `shared.services.calculator.prompts.load_calculator_prompts` so an unseeded
PROJECT_CONTEXT_RESOLVE prompt never breaks a position calculation: the resolver loads it only
when it actually runs a live (non-mock) resolution.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import PromptType
from shared.models.prompt_version import PromptVersion
from shared.repositories.prompt_versions import PromptVersionRepository


class ProjectContextPromptNotSeededError(Exception):
    """PROJECT_CONTEXT_RESOLVE has no version in prompt_versions (run scripts.seed.prompts)."""


async def load_resolve_prompt(conn: AsyncConnection) -> PromptVersion:
    pv = await PromptVersionRepository(conn).get_latest(PromptType.PROJECT_CONTEXT_RESOLVE)
    if pv is None:
        raise ProjectContextPromptNotSeededError(
            "no prompt version for project_context_resolve; run `python -m scripts.seed.prompts`"
        )
    return pv
