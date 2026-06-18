"""Load the EKT calculation graph's DB-backed prompt versions.

The graph's structured LLM sites (classify, driver resolution, method selection) and the
pre-run chat-seed extractor each run on a versioned prompt stored in `prompt_versions`,
seeded from the `ekt_*.prompt` files. This loads the latest version of each in one short
connection up front, so the graph nodes themselves never touch the DB (they receive the
resolved PromptVersions) and no connection is held across the streamed run.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import PromptType
from shared.models.prompt_version import PromptVersion
from shared.repositories.prompt_versions import PromptVersionRepository

# The prompt types the calculator resolves. CLASSIFY/RESOLVE_DRIVER/SELECT_METHOD drive the
# graph nodes; SEED_DRIVERS runs once before the graph (lifting chat-set driver values).
EKT_PROMPT_TYPES = (
    PromptType.EKT_CLASSIFY,
    PromptType.EKT_RESOLVE_DRIVER,
    PromptType.EKT_SELECT_METHOD,
    PromptType.EKT_SEED_DRIVERS,
)


class CalculatorPromptNotSeededError(Exception):
    """A calculator prompt type has no version in prompt_versions (run scripts.seed.prompts)."""


async def load_calculator_prompts(
    conn: AsyncConnection,
) -> dict[PromptType, PromptVersion]:
    """Return the latest version of every calculator prompt type, keyed by type."""
    repo = PromptVersionRepository(conn)
    prompts: dict[PromptType, PromptVersion] = {}
    for prompt_type in EKT_PROMPT_TYPES:
        pv = await repo.get_latest(prompt_type)
        if pv is None:
            raise CalculatorPromptNotSeededError(
                f"no prompt version for {prompt_type.value}; run `python -m scripts.seed.prompts`"
            )
        prompts[prompt_type] = pv
    return prompts
