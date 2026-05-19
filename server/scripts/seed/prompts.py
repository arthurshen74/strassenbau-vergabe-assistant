from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from shared.config import settings
from shared.db.engine import make_engine
from shared.db.tables.prompt_versions import prompt_versions
from shared.db.tables.prompts import prompts


@dataclass(frozen=True)
class PromptSeed:
    slug: str
    description: str
    system_prompt: str
    model_provider: str = "anthropic"
    model_id: str = "claude-sonnet-4-6"
    api_key_ref: str = "ANTHROPIC_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 4096
    output_schema_ref: str | None = None


SEEDS: tuple[PromptSeed, ...] = (
    PromptSeed(
        slug="vision_lv_page",
        description="Vision extraction for Leistungsverzeichnis pages.",
        system_prompt=(
            "You extract LV items from a single Leistungsverzeichnis page. "
            "Return one structured row per item."
        ),
    ),
    PromptSeed(
        slug="vision_prose_page",
        description="Vision extraction for prose specification pages.",
        system_prompt=(
            "You extract paragraphs and headings from a single prose "
            "specification page."
        ),
    ),
    PromptSeed(
        slug="extract_assertions",
        description="Extract atomic assertions from a paragraph of text.",
        system_prompt=(
            "You decompose a paragraph into atomic, self-contained "
            "assertions about the construction project."
        ),
    ),
    PromptSeed(
        slug="chat_rag",
        description="Chat RAG synthesis over retrieved evidence.",
        system_prompt=(
            "You answer questions about the construction project using only "
            "the provided evidence. Cite each claim."
        ),
    ),
    PromptSeed(
        slug="eval_grader",
        description="Grader prompt for eval item correctness.",
        system_prompt=(
            "You compare a model answer to an expected answer and return a "
            "structured grading verdict."
        ),
    ),
)


async def _seed(conn: AsyncConnection) -> None:
    for seed in SEEDS:
        upsert = (
            pg_insert(prompts)
            .values(slug=seed.slug, description=seed.description)
            .on_conflict_do_update(
                index_elements=[prompts.c.slug],
                set_={"description": seed.description, "updated_at": func.now()},
            )
            .returning(prompts.c.prompt_uuid)
        )
        prompt_uuid = (await conn.execute(upsert)).scalar_one()

        existing = (
            await conn.execute(
                select(func.count())
                .select_from(prompt_versions)
                .where(prompt_versions.c.prompt_uuid == prompt_uuid)
            )
        ).scalar_one()
        action = "kept"
        if existing == 0:
            await conn.execute(
                pg_insert(prompt_versions).values(
                    prompt_uuid=prompt_uuid,
                    version=1,
                    system_prompt=seed.system_prompt,
                    model_provider=seed.model_provider,
                    model_id=seed.model_id,
                    api_key_ref=seed.api_key_ref,
                    temperature=seed.temperature,
                    max_tokens=seed.max_tokens,
                    output_schema_ref=seed.output_schema_ref,
                )
            )
            action = "seeded v1"
        print(f"  {seed.slug}: {action}")


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
