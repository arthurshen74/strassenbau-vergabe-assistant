"""Execution surface for DB-stored prompts.

PromptRunner is the one place that turns a PromptType into an LLM call: it loads the prompt
version, renders its `{{placeholder}}` template, resolves the registered output schema, and
delegates to the generic LLMClient (which records usage). The typed wrappers below are the
public surface feature code calls; `_run` is the shared mechanism beneath them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from uuid import UUID

from pydantic import BaseModel

from shared.clients.llm import LLMClient
from shared.config import settings
from shared.models.chat_message import ChatMessage
from shared.models.enums import PromptType
from shared.models.llm_output_schemas import (
    LVExtraction,
    LVMembership,
    MultiQueryRewrite,
    output_model_for,
)
from shared.repositories.prompt_versions import PromptVersionRepository

# OpenRouter message keys and the system role. ChatMessage only models user/assistant turns,
# so the rendered system prompt is passed as a plain message mapping.
MESSAGE_ROLE = "role"
MESSAGE_CONTENT = "content"
ROLE_SYSTEM = "system"

# Matches a {{ name }} placeholder in a prompt template.
_PLACEHOLDER_RE = re.compile(r"{{\s*(\w+)\s*}}")


class PromptVersionNotFoundError(Exception):
    """No PromptVersion exists for the requested prompt type (and version)."""


class PromptRenderError(Exception):
    """A prompt template has a placeholder with no supplied variable."""


class PromptRunner:
    """Loads a prompt version, renders it, and runs it through the LLM transport."""

    def __init__(self, prompts: PromptVersionRepository, llm: LLMClient) -> None:
        self._prompts = prompts
        self._llm = llm

    async def generate_query_variants(
        self,
        query: str,
        *,
        n: int | None = None,
        version: int | None = None,
        project_uuid: UUID | None = None,
        ingest_job_uuid: UUID | None = None,
        conversation_uuid: UUID | None = None,
    ) -> list[str]:
        """Expand a query into up to `n` retrieval variants via the multi-question generator."""
        count = n if n is not None else settings.multi_query_n
        result = await self._run(
            PromptType.MULTI_QUESTION_GENERATOR,
            variables={"n": str(count)},
            messages=[ChatMessage(role="user", content=query)],
            version=version,
            project_uuid=project_uuid,
            ingest_job_uuid=ingest_job_uuid,
            conversation_uuid=conversation_uuid,
        )
        assert isinstance(result, MultiQueryRewrite)
        return result.queries[:count]

    async def run_lv_membership(
        self,
        predicate: str,
        listing: str,
        *,
        version: int | None = None,
        project_uuid: UUID | None = None,
        conversation_uuid: UUID | None = None,
    ) -> LVMembership:
        """Decide which LV positions in `listing` match an aggregation `predicate` (membership
        only; the caller sums the matched items deterministically)."""
        result = await self._run(
            PromptType.AGGREGATE_LV_MEMBERSHIP,
            variables={"predicate": predicate, "listing": listing},
            version=version,
            project_uuid=project_uuid,
            conversation_uuid=conversation_uuid,
        )
        assert isinstance(result, LVMembership)
        return result

    async def run_lv_extraction(
        self,
        numbered_document: str,
        *,
        version: int | None = None,
        project_uuid: UUID | None = None,
        ingest_job_uuid: UUID | None = None,
        document_uuid: UUID | None = None,
    ) -> LVExtraction:
        """Segment a line-numbered LV rendering into positions (LV_PARSE.md step 3)."""
        result = await self._run(
            PromptType.LV_EXTRACTION,
            variables={"numbered_document": numbered_document},
            version=version,
            project_uuid=project_uuid,
            ingest_job_uuid=ingest_job_uuid,
            document_uuid=document_uuid,
        )
        assert isinstance(result, LVExtraction)
        return result

    async def run_text(
        self,
        prompt_type: PromptType,
        *,
        messages: Sequence[ChatMessage],
        variables: Mapping[str, str] | None = None,
        version: int | None = None,
        project_uuid: UUID | None = None,
        ingest_job_uuid: UUID | None = None,
    ) -> str:
        """Run a free-form (non-structured) prompt type and return the assistant text."""
        result = await self._run(
            prompt_type,
            variables=variables,
            messages=messages,
            version=version,
            project_uuid=project_uuid,
            ingest_job_uuid=ingest_job_uuid,
        )
        assert isinstance(result, str)
        return result

    async def _run(
        self,
        prompt_type: PromptType,
        *,
        variables: Mapping[str, str] | None = None,
        messages: Sequence[ChatMessage] = (),
        version: int | None = None,
        project_uuid: UUID | None = None,
        ingest_job_uuid: UUID | None = None,
        document_uuid: UUID | None = None,
        conversation_uuid: UUID | None = None,
    ) -> str | BaseModel:
        pv = (
            await self._prompts.get_latest(prompt_type)
            if version is None
            else await self._prompts.get_by_type_and_version(prompt_type, version)
        )
        if pv is None:
            raise PromptVersionNotFoundError(
                f"no prompt version for type={prompt_type.value} version={version}"
            )

        system = render_template(pv.system_prompt, variables)
        chat_messages: list[ChatMessage | Mapping[str, str]] = [
            {MESSAGE_ROLE: ROLE_SYSTEM, MESSAGE_CONTENT: system},
            *messages,
        ]
        output_model = output_model_for(prompt_type)
        # Split on output_model so chat()'s overloads resolve to str vs the validated model.
        if output_model is None:
            return await self._llm.chat(
                model=pv.model_name,
                messages=chat_messages,
                temperature=pv.temperature,
                top_p=pv.top_p,
                chat_prompt_type=prompt_type.value,
                chat_prompt_version=pv.version,
                project_uuid=project_uuid,
                ingest_job_uuid=ingest_job_uuid,
            )
        return await self._llm.chat(
            model=pv.model_name,
            messages=chat_messages,
            output_model=output_model,
            temperature=pv.temperature,
            top_p=pv.top_p,
            chat_prompt_type=prompt_type.value,
            chat_prompt_version=pv.version,
            project_uuid=project_uuid,
            ingest_job_uuid=ingest_job_uuid,
            document_uuid=document_uuid,
            conversation_uuid=conversation_uuid,
        )


def render_template(template: str, variables: Mapping[str, str] | None) -> str:
    """Substitute `{{name}}` placeholders; raise if any placeholder has no supplied variable."""
    values = variables or {}

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise PromptRenderError(f"missing variable for placeholder {{{{{name}}}}}")
        return values[name]

    return _PLACEHOLDER_RE.sub(replace, template)
