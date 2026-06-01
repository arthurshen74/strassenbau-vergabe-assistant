"""Seed one v1 PromptVersion per PromptType.

Idempotent: the insert conflicts on the (prompt_type, version) unique and does
nothing on re-run, so it never appends a v2. Run with
`python -m scripts.seed.prompts` (or via docker compose against the compose DB).
"""

from __future__ import annotations

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from shared.config import settings
from shared.db.engine import make_engine
from shared.db.tables.prompt_versions import prompt_versions
from shared.models.enums import PromptType

SEED_VERSION = 1
MODEL_NAME = "anthropic/claude-sonnet-4.6"
TEMPERATURE = 0.0

SYSTEM_PROMPTS: dict[PromptType, str] = {
    PromptType.DISPATCHER: (
        "You route an incoming user request to the appropriate downstream skill."
    ),
    PromptType.PROJECT_CHAT: (
        "You answer questions about the construction project using only the "
        "provided evidence. Cite each claim."
    ),
    PromptType.CLASSIFY_PROJECT_CHAT_USER_MESSAGE: (
        "You classify a user's chat message into the correct project-chat intent."
    ),
    PromptType.MULTI_QUESTION_GENERATOR: (
        "You rewrite a search query into {{n}} diverse alternative phrasings that a "
        "retrieval system can use to find relevant passages. Preserve the original intent "
        "while varying wording, specificity, and synonyms. Return exactly {{n}} variants."
    ),
    PromptType.LV_EXTRACTION: (
        "You extract Leistungsverzeichnis items from a document page as "
        "structured rows."
    ),
}


async def _seed(conn: AsyncConnection) -> None:
    for prompt_type in PromptType:
        upsert = (
            pg_insert(prompt_versions)
            .values(
                prompt_type=prompt_type.value,
                version=SEED_VERSION,
                model_name=MODEL_NAME,
                system_prompt=SYSTEM_PROMPTS[prompt_type],
                temperature=TEMPERATURE,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    prompt_versions.c.prompt_type,
                    prompt_versions.c.version,
                ]
            )
            .returning(prompt_versions.c.prompt_version_uuid)
        )
        inserted = (await conn.execute(upsert)).first()
        action = "seeded v1" if inserted else "kept"
        print(f"  {prompt_type.value}: {action}")


async def main() -> None:
    engine: AsyncEngine = make_engine(
        settings.database_url, pool_size=2, application_name="seed-prompts"
    )
    try:
        async with engine.begin() as conn:
            await _seed(conn)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
