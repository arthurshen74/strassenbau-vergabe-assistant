"""The project-chat ReAct agent.

A `create_agent` tool-calling loop, scoped to one project, that streams its answer. It replaces the
old classify -> route pipeline: the model decides which of seven tools to call, in any order, across a
multi-turn conversation. Retrieval tools reuse the Simple/Plus `RetrievalService` (honoring the
turn's `RetrievalConfig`); LV tools read the LV item repository; `aggregate_lv_items` totals
quantities via `AggregateLVService` (the LLM judges membership, Python sums). The answer model is a
streaming `ChatOpenAI` whose usage/execution telemetry is buffered by `TelemetryCallbackHandler` and
drained by the caller after the run (the engine's sinks are bound to the main loop).

`astream` seeds the agent with the conversation's prior user/assistant turns and relays three event
kinds to the service: answer tokens, tool calls, and tool results. Citation numbers are offset across
context-tool calls so the answer's [n] references stay unique within a turn.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.utils import convert_to_secret_str
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.clients.llm.execution_log import ExecutionLogEvent
from shared.clients.llm.langchain_callback import TelemetryCallbackHandler
from shared.clients.maps.client import (
    MAP_CONTENT_TYPE,
    MAPTYPE_ROADMAP,
    StaticMapError,
    fetch_static_map_png,
    static_map_id,
)
from shared.clients.openrouter.usage import UsageEvent
from shared.clients.search import lv_items_filter
from shared.clients.storage.client import StorageClient, map_object_key
from shared.config import settings
from shared.models.enums import RetrievalModality
from shared.models.lv_item import LVItem
from shared.repositories.lv_items import LVItemRepository
from shared.services.aggregate_lv import AggregateLVService
from shared.services.aggregate_lv_models import AggregateResult
from shared.services.retrieval import RetrievalConfig, RetrievalError, RetrievalService
from shared.services.retrieval.service import format_context

# OpenRouter usage-accounting opt-in; without it the chat response carries no cost.
USAGE_ACCOUNTING_EXTRA_BODY = {"usage": {"include": True}}

# The ChatOpenAI base_url is the chat-completions URL without its endpoint suffix; one settings value
# is the source of truth for the OpenRouter host.
_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"

# Wire tool names the model sees and the SSE function_call/_output rows carry. The UI
# (ToolResultMessage) renders each result by these names.
TOOL_GET_PROJECT_CONTEXT = "get_project_context"
TOOL_GET_LV_CONTEXT = "get_lv_context"
TOOL_GET_LV_ALL = "get_lv_all"
TOOL_GET_LV_SINGLE_ITEM = "get_lv_single_item"
TOOL_GET_LV_GROUP_ITEMS = "get_lv_group_items"
TOOL_AGGREGATE_LV_ITEMS = "aggregate_lv_items"
TOOL_RENDER_MAP = "render_map"

# Tool-result payload keys the UI reads out of `data`.
RESULT_LV_ITEM = "lv_item"
RESULT_LV_ITEMS = "lv_items"
RESULT_MAP_ID = "map_id"
RESULT_MAP_ADDRESS = "address"
RESULT_MAP_ZOOM = "zoom"
RESULT_MAP_ERROR = "error"

# astream_events v2 keys we relay to SSE. run_id is shared by a tool call's start and end events,
# so it pairs a tool call with its result even when several tools run in one assistant turn.
EV_EVENT = "event"
EV_NAME = "name"
EV_RUN_ID = "run_id"
EV_DATA = "data"
EV_CHUNK = "chunk"
EV_INPUT = "input"
EV_OUTPUT = "output"
EV_CHAT_MODEL_STREAM = "on_chat_model_stream"
EV_TOOL_START = "on_tool_start"
EV_TOOL_END = "on_tool_end"


class AgentToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


class AgentToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    name: str
    arguments: dict[str, Any]


class AgentToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    name: str
    payload: dict[str, Any]


# One step of the streamed agent run: an answer token, a tool call, or a tool result.
AgentEvent = AgentToken | AgentToolCall | AgentToolResult


def _openrouter_base_url() -> str:
    return settings.openrouter_api_url_chat.removesuffix(_CHAT_COMPLETIONS_SUFFIX)


class ProjectChatAgent:
    """A project-scoped ReAct agent over seven tools that streams its answer token-by-token."""

    def __init__(
        self,
        *,
        project_uuid: UUID,
        config: RetrievalConfig,
        engine: AsyncEngine,
        retrieval: RetrievalService,
        aggregate: AggregateLVService,
        storage: StorageClient,
        system_prompt: str,
        chat_model: str,
        temperature: float | None,
        prompt_type: str,
        conversation_uuid: UUID | None = None,
    ) -> None:
        self._project_uuid = project_uuid
        self._conversation_uuid = conversation_uuid
        self._config = config
        self._engine = engine
        self._retrieval = retrieval
        self._aggregate = aggregate
        self._storage = storage
        self._telemetry = TelemetryCallbackHandler(
            project_uuid=project_uuid,
            prompt_type=prompt_type,
            provider_url=_openrouter_base_url(),
            chat_model=chat_model,
            conversation_uuid=conversation_uuid,
        )
        # Running citation offset so [n] numbers stay unique across multiple context-tool calls.
        self._cite_offset = 0

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
        self._agent = create_agent(model, self._build_tools(), system_prompt=system_prompt)

    def _build_tools(self) -> list[Any]:
        @tool(TOOL_GET_PROJECT_CONTEXT, response_format="content_and_artifact")
        async def get_project_context(query: str) -> tuple[str, dict[str, Any]]:
            """Semantic search across all of the project's documents (prose and LV). Returns numbered
            evidence sources for grounding the answer with [n] citations."""
            return await self._retrieve(query, scope_override=None)

        @tool(TOOL_GET_LV_CONTEXT, response_format="content_and_artifact")
        async def get_lv_context(query: str) -> tuple[str, dict[str, Any]]:
            """Semantic search restricted to the project's LV positions. Returns numbered evidence
            sources for grounding the answer with [n] citations."""
            return await self._retrieve(
                query, scope_override=lv_items_filter(self._project_uuid)
            )

        @tool(TOOL_GET_LV_ALL, response_format="content_and_artifact")
        async def get_lv_all() -> tuple[str, dict[str, Any]]:
            """Every LV position in the project (OZ, Kurztext, Menge, Einheit). Large; prefer the
            narrower LV tools unless the whole list is genuinely needed."""
            async with self._engine.connect() as conn:
                items = await LVItemRepository(conn).list_by_project(self._project_uuid)
            return _format_items(items), {RESULT_LV_ITEMS: _dump_items(items)}

        @tool(TOOL_GET_LV_SINGLE_ITEM, response_format="content_and_artifact")
        async def get_lv_single_item(oz: str) -> tuple[str, dict[str, Any]]:
            """One LV position by its exact Ordnungszahl (e.g. '01.02.0030')."""
            async with self._engine.connect() as conn:
                item = await LVItemRepository(conn).get_by_project_and_oz(
                    self._project_uuid, oz
                )
            content = (
                f"Position {item.oz}: {item.kurztext} — {item.menge} {item.einheit}"
                if item is not None
                else f"Keine Position zur Ordnungszahl {oz} gefunden."
            )
            return content, {RESULT_LV_ITEM: item.model_dump(mode="json") if item else None}

        @tool(TOOL_GET_LV_GROUP_ITEMS, response_format="content_and_artifact")
        async def get_lv_group_items(parent_oz: str) -> tuple[str, dict[str, Any]]:
            """Every LV position under a section / branch OZ (e.g. '01.02')."""
            async with self._engine.connect() as conn:
                items = await LVItemRepository(conn).list_by_parent_oz(
                    self._project_uuid, parent_oz
                )
            return _format_items(items), {RESULT_LV_ITEMS: _dump_items(items)}

        @tool(TOOL_AGGREGATE_LV_ITEMS, response_format="content_and_artifact")
        async def aggregate_lv_items(
            predicate: str, unit: str | None = None
        ) -> tuple[str, dict[str, Any]]:
            """Total the quantity (Menge) across the LV positions matching a predicate, grouped by
            unit. Use for any 'how much / total / Gesamtmenge' question. `predicate` names what to
            sum (e.g. 'Bodenabtrag / earth removal'); `unit` optionally restricts the subtotal."""
            result = await self._aggregate.aggregate(
                predicate, self._project_uuid, unit, conversation_uuid=self._conversation_uuid
            )
            return _format_aggregate(result), result.model_dump(mode="json")

        @tool(TOOL_RENDER_MAP, response_format="content_and_artifact")
        async def render_map(
            address: str, zoom: int | None = None, maptype: str = MAPTYPE_ROADMAP
        ) -> tuple[str, dict[str, Any]]:
            """Render an 800x800 map image for a street address and show it in the chat. `zoom`
            defaults to the configured project zoom (a ~3 km radius); pass a higher number to zoom
            in. `maptype` is roadmap (default), satellite, hybrid, or terrain. Use whenever the
            user asks to see, show, or render a location / site on a map."""
            effective_zoom = zoom if zoom is not None else settings.static_map_zoom
            try:
                png = await fetch_static_map_png(address, zoom=effective_zoom, maptype=maptype)
            except StaticMapError as exc:
                return f"Karte konnte nicht erzeugt werden: {exc}", {RESULT_MAP_ERROR: str(exc)}
            map_id = static_map_id(address, effective_zoom, maptype)
            key = map_object_key(self._project_uuid, map_id)
            await asyncio.to_thread(self._storage.put_object, key, png, MAP_CONTENT_TYPE)
            return (
                f"Karte für {address} erstellt.",
                {
                    RESULT_MAP_ID: map_id,
                    RESULT_MAP_ADDRESS: address,
                    RESULT_MAP_ZOOM: effective_zoom,
                },
            )

        return [
            get_project_context,
            get_lv_context,
            get_lv_all,
            get_lv_single_item,
            get_lv_group_items,
            aggregate_lv_items,
            render_map,
        ]

    async def _retrieve(
        self, query: str, *, scope_override: dict[str, Any] | None
    ) -> tuple[str, dict[str, Any]]:
        try:
            ctx = await self._retrieval.retrieve_context(
                query,
                self._project_uuid,
                self._config,
                scope_override=scope_override,
                conversation_uuid=self._conversation_uuid,
            )
        except RetrievalError:
            # PLUS needs an LV document; fall back to SIMPLE rather than failing the tool call.
            fallback = self._config.model_copy(update={"modality": RetrievalModality.SIMPLE})
            ctx = await self._retrieval.retrieve_context(
                query,
                self._project_uuid,
                fallback,
                scope_override=scope_override,
                conversation_uuid=self._conversation_uuid,
            )
        # Offset source numbers so [n] citations stay unique across multiple context calls this turn.
        renumbered = [
            c.model_copy(update={"source_number": c.source_number + self._cite_offset})
            for c in ctx.context
        ]
        self._cite_offset += len(ctx.context)
        ctx = ctx.model_copy(update={"context": renumbered})
        return format_context(ctx.context), ctx.model_dump(mode="json")

    async def astream(self, messages: list[dict[str, Any]]) -> AsyncIterator[AgentEvent]:
        """Stream the agent over the prior message list: answer tokens, tool calls, tool results."""
        async for event in self._agent.astream_events({"messages": messages}, version="v2"):
            mapped = map_agent_event(event)
            if mapped is not None:
                yield mapped

    def drain_telemetry(self) -> tuple[list[UsageEvent], list[ExecutionLogEvent]]:
        """Return the usage + execution-log events buffered since the last drain, and clear them."""
        return self._telemetry.drain()


def map_agent_event(event: dict[str, Any]) -> AgentEvent | None:
    """Map one astream_events v2 event to an AgentEvent, or None for events we don't relay."""
    kind = event.get(EV_EVENT)
    data = event.get(EV_DATA)
    if not isinstance(data, dict):
        return None
    if kind == EV_CHAT_MODEL_STREAM:
        text = _chunk_text(data.get(EV_CHUNK))
        return AgentToken(content=text) if text else None
    if kind == EV_TOOL_START:
        name = event.get(EV_NAME)
        if not isinstance(name, str):
            return None
        tool_input = data.get(EV_INPUT)
        return AgentToolCall(
            call_id=_run_id(event),
            name=name,
            arguments=tool_input if isinstance(tool_input, dict) else {},
        )
    if kind == EV_TOOL_END:
        name = event.get(EV_NAME)
        if not isinstance(name, str):
            return None
        return AgentToolResult(
            call_id=_run_id(event), name=name, payload=_tool_payload(data.get(EV_OUTPUT))
        )
    return None


def _dump_items(items: list[LVItem]) -> list[dict[str, Any]]:
    return [i.model_dump(mode="json") for i in items]


def _format_items(items: list[LVItem]) -> str:
    if not items:
        return "Keine Positionen gefunden."
    return "\n".join(
        f"{i.oz} | {i.kurztext} | {i.menge} {i.einheit}" for i in items
    )


def _format_aggregate(result: AggregateResult) -> str:
    if not result.per_unit and not result.bedarfs_eventual:
        return (
            f"Keine Positionen für '{result.predicate}' gefunden "
            f"({result.coverage.matched} von {result.coverage.total})."
        )
    subtotals = "; ".join(f"{s.total} {s.einheit} (aus {s.count} Positionen)" for s in result.per_unit)
    out = (
        f"Summe für '{result.predicate}': {subtotals or 'keine regulären Positionen'}. "
        f"Abgedeckt: {result.coverage.matched} von {result.coverage.total} Positionen."
    )
    if result.bedarfs_eventual:
        out += (
            f" Zusätzlich {len(result.bedarfs_eventual)} Bedarfs-/Eventualposition(en) "
            "separat ausgewiesen."
        )
    return out


def _chunk_text(chunk: Any) -> str:
    """The text of a streamed model chunk. `content` is a str for text models, or a list of content
    blocks for some providers; join the text blocks in that case."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part for part in content if isinstance(part, str))
    return ""


def _tool_payload(output: Any) -> dict[str, Any]:
    """The artifact dict a content_and_artifact tool returned, carried on the ToolMessage."""
    artifact = getattr(output, "artifact", None)
    return artifact if isinstance(artifact, dict) else {}


def _run_id(event: dict[str, Any]) -> str:
    """The event's run_id as the call_id pairing a tool call with its result; a fresh uuid if absent."""
    run_id = event.get(EV_RUN_ID)
    return str(run_id) if run_id else str(uuid4())
