from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import anthropic
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.llm.client import LLMClient
from shared.prompts.registry import resolve_output_schema
from shared.prompts.tokens import substitute
from shared.repositories.prompts import PromptRepository


@dataclass(frozen=True)
class InvocationMeta:
    prompt_uuid: UUID
    version: int
    model_id: str
    elapsed_seconds: float
    usage: dict[str, int]


class PromptNotFoundError(LookupError):
    pass


class MissingApiKeyError(RuntimeError):
    pass


async def invoke(
    prompt_slug: str,
    *,
    conn: AsyncConnection,
    version: int | Literal["latest"] = "latest",
    tokens: dict[str, str] | None = None,
    user_content: str | list[dict[str, Any]],
) -> tuple[BaseModel, InvocationMeta]:
    pv = await PromptRepository(conn).get_version_by_slug(prompt_slug, version)
    if pv is None:
        raise PromptNotFoundError(
            f"prompt {prompt_slug!r} version {version!r} not found"
        )

    output_model = resolve_output_schema(pv.output_schema_ref)
    if output_model is None:
        raise NotImplementedError(
            f"prompt {prompt_slug!r} has no output_schema_ref; "
            "schemaless invocation is not yet supported"
        )
    if pv.tool_selection:
        raise NotImplementedError(
            f"prompt {prompt_slug!r} declares tool_selection; "
            "tool-using invocation is not yet supported"
        )

    api_key = os.environ.get(pv.api_key_ref)
    if not api_key:
        raise MissingApiKeyError(
            f"environment variable {pv.api_key_ref!r} is not set"
        )

    system = substitute(pv.system_prompt, tokens)

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if pv.model_endpoint:
        client_kwargs["base_url"] = pv.model_endpoint
    llm = LLMClient(anthropic.Anthropic(**client_kwargs))

    def _call() -> tuple[BaseModel, float, str]:
        return llm.call(
            models=pv.model_id,
            system=system,
            user_content=user_content,
            output_model=output_model,
            max_tokens=pv.max_tokens,
            temperature=pv.temperature,
            stop_sequences=pv.stop_sequences,
            where=f"prompt:{prompt_slug}:v{pv.version}",
        )

    parsed, elapsed, model_used = await asyncio.to_thread(_call)
    meta = InvocationMeta(
        prompt_uuid=pv.prompt_uuid,
        version=pv.version,
        model_id=model_used,
        elapsed_seconds=elapsed,
        usage=llm.usage_summary(),
    )
    return parsed, meta
