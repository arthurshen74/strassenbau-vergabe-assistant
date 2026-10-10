"""The synthesis LLM site for one project header field (PROJECT_INFO_RESOLVE).

`resolve_project_info` distills the hybrid-RAG chunks for ONE project-info query into a
structured `{wert, konfidenz, beleg}` (reasoning-augmented), one query per call like
`shared.services.project_context.llm.resolve_globale`. The query's `answer_instruction`
sets the value format; its `query_text` only drove retrieval and is not sent.
"""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import BaseModel, Field

from shared.clients.llm.client import (
    MESSAGE_CONTENT,
    MESSAGE_ROLE,
    ROLE_SYSTEM,
    ROLE_USER,
    LLMClient,
)
from shared.models.prompt_version import PromptVersion
from shared.models.rag_query import RagQueryVersion

_REASONING = (
    "2-5 kurze Denkschritte, ZUERST: was die Auszüge sagen -> welche Stelle den Wert "
    "hergibt -> Schluss. Belege mit wörtlichem Zitat."
)


class ProjektInfoAufloesung(BaseModel):
    reasoning: list[str] = Field(default=[], description=_REASONING)
    gefunden: bool = Field(
        description="True nur, wenn die Auszüge den Wert eindeutig hergeben"
    )
    wert: str | None = Field(
        default=None,
        description="Der Wert im Format der answer_instruction; None wenn nicht "
        "gefunden",
    )
    konfidenz: float = Field(ge=0, le=1)
    beleg: str | None = Field(
        default=None, description="Wörtliches Belegzitat aus den Auszügen"
    )


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [
        {MESSAGE_ROLE: ROLE_SYSTEM, MESSAGE_CONTENT: system},
        {MESSAGE_ROLE: ROLE_USER, MESSAGE_CONTENT: user},
    ]


def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


async def resolve_project_info(
    llm: LLMClient,
    query: RagQueryVersion,
    snippets: list[str],
    *,
    prompt: PromptVersion,
    project_uuid: UUID,
) -> tuple[ProjektInfoAufloesung, str | None]:
    """Synthesize one project header field from its retrieved snippets."""
    gesucht = {
        "name": query.name,
        "description": query.description,
        "answer_instruction": query.answer_instruction,
        "language": query.language,
    }
    user = (
        f"Gesuchtes Projektfeld:\n{_dump(gesucht)}\n\n"
        f"Auszüge (verwende NUR diese):\n{_dump(snippets)}"
    )
    return await llm.chat_with_reasoning(
        model=prompt.model_name,
        messages=_messages(prompt.system_prompt, user),
        output_model=ProjektInfoAufloesung,
        temperature=prompt.temperature,
        reasoning_effort=prompt.reasoning_effort,
        strict=False,
        chat_prompt_type=prompt.prompt_type.value,
        chat_prompt_version=prompt.version,
        project_uuid=project_uuid,
    )
