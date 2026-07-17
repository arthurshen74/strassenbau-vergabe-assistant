"""Load the Katalog-Handbuch — the katalog_chat agent's system prompt.

A lazy loader (mirrors `project_context.prompts.load_resolve_prompt`) so an unseeded
KATALOG_HANDBUCH never breaks unrelated flows: the katalog chat loads it only when it
runs a turn. The prompt frontmatter owns the model choice, so the loaded `PromptVersion`
carries both the system prompt and the model/temperature the agent uses (§3) — edit +
re-seed in the prompt editor and the next turn (and the recipe-compiler eval) picks up
the new version.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import PromptType
from shared.models.prompt_version import PromptVersion
from shared.repositories.prompt_versions import PromptVersionRepository


class KatalogHandbuchNotSeededError(Exception):
    """KATALOG_HANDBUCH has no version in prompt_versions (run scripts.seed.prompts)."""


async def load_katalog_handbuch_prompt(conn: AsyncConnection) -> PromptVersion:
    pv = await PromptVersionRepository(conn).get_latest(PromptType.KATALOG_HANDBUCH)
    if pv is None:
        raise KatalogHandbuchNotSeededError(
            "no prompt version for katalog_handbuch; run `python -m "
            "scripts.seed.prompts`"
        )
    return pv
