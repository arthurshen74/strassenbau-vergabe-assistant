"""The katalog_chat ReAct agent — a `create_agent` tool loop over the read-only Katalog tools.

The catalog analogue of `ProjectChatAgent`: a streaming `ChatOpenAI` (OpenRouter) that decides which
of the T1–T33 read tools to call and streams a grounded German answer. It is not project-scoped (the
catalog is global), so it carries no retrieval/LV surface — only the `katalog_werkzeuge` and the
Katalog-Handbuch system prompt. Usage/execution telemetry is buffered by a `TelemetryCallbackHandler`
and drained after the run; `astream_events` is relayed through the shared `map_agent_event` mapping,
so the SSE protocol and UI rendering are identical to the project chat's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from langchain.agents import create_agent
from langchain_core.utils import convert_to_secret_str
from langchain_openai import ChatOpenAI

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.execution_log import ExecutionLogEvent
from shared.clients.llm.langchain_callback import TelemetryCallbackHandler
from shared.clients.openrouter.usage import UsageEvent
from shared.config import settings
from shared.models.enums import PromptType
from shared.services.katalog.werkzeuge import katalog_werkzeuge
from shared.services.katalog.werkzeuge_rezept import katalog_rezept_werkzeuge
from shared.services.katalog.werkzeuge_schreiben import katalog_schreib_werkzeuge
from shared.services.project_chat_agent import (
    USAGE_ACCOUNTING_EXTRA_BODY,
    AgentEvent,
    map_agent_event,
)

# The ChatOpenAI base_url is the chat-completions URL without its endpoint suffix (same settings
# value that is the source of truth for the OpenRouter host).
_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"


def _openrouter_base_url() -> str:
    return settings.openrouter_api_url_chat.removesuffix(_CHAT_COMPLETIONS_SUFFIX)


class KatalogChatAgent:
    """A ReAct agent over the read-only catalog tools that streams its answer token-by-token."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        system_prompt: str,
        chat_model: str,
        temperature: float | None,
        conversation_uuid: UUID | None = None,
    ) -> None:
        self._telemetry = TelemetryCallbackHandler(
            prompt_type=PromptType.KATALOG_CHAT.value,
            provider_url=_openrouter_base_url(),
            chat_model=chat_model,
            conversation_uuid=conversation_uuid,
        )
        model = ChatOpenAI(
            model=chat_model,
            base_url=_openrouter_base_url(),
            api_key=convert_to_secret_str(settings.openrouter_api_key or ""),
            temperature=temperature,
            extra_body=USAGE_ACCOUNTING_EXTRA_BODY,
            callbacks=[self._telemetry],
            streaming=True,
            stream_usage=True,
        )
        werkzeuge = (
            katalog_werkzeuge(engine)
            + katalog_schreib_werkzeuge(engine)
            + katalog_rezept_werkzeuge(engine)
        )
        self._agent = create_agent(model, werkzeuge, system_prompt=system_prompt)

    async def astream(self, messages: list[dict[str, Any]]) -> AsyncIterator[AgentEvent]:
        """Stream the agent over the prior message list: answer tokens, tool calls, tool results."""
        async for event in self._agent.astream_events({"messages": messages}, version="v2"):  # type: ignore
            mapped = map_agent_event(event)
            if mapped is not None:
                yield mapped

    async def ainvoke(
        self, messages: list[dict[str, Any]], recursion_limit: int = 25
    ) -> dict[str, Any]:
        """Run the agent to completion and return the final graph state (`messages` includes the
        AI tool calls and ToolMessages with artifacts). The non-SSE path, used by the eval harness."""
        return await self._agent.ainvoke(
            {"messages": messages}, config={"recursion_limit": recursion_limit}
        )

    def drain_telemetry(self) -> tuple[list[UsageEvent], list[ExecutionLogEvent]]:
        """Return the usage + execution-log events buffered since the last drain, and clear them."""
        return self._telemetry.drain()
