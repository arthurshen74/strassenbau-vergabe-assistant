"""Dispatcher tool catalogs keyed by PromptType.

Mirrors the output-schema registry: the single place that declares which tools each
dispatcher advertises. Handlers call repositories directly via the `ToolContext`.
Project chat does not run this loop — it is driven by `ProjectChatService` (classify ->
retrieve -> answer), not the dispatcher — so only the dispatcher prompt type has a
catalog here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.models.enums import PromptType
from shared.models.ingest_schema import ConsoleJobRead
from shared.models.openrouter_usage_schema import OpenRouterUsageRead
from shared.models.prompt_execution_log_schema import PromptExecutionLogSummary
from shared.tools._base import ToolContext, ToolDefinition

# Rows a log tool surfaces to the dispatcher (recent-first); the UI views page/filter
# via REST.
_LOG_TOOL_LIMIT = 50


class _NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def _view_projects(_args: _NoArgs, ctx: ToolContext) -> dict[str, object]:
    projects = await ctx.uow.projects.list()
    return {"projects": [p.model_dump(mode="json") for p in projects]}


async def _view_prompts(_args: _NoArgs, ctx: ToolContext) -> dict[str, object]:
    latest = []
    for prompt_type in PromptType:
        pv = await ctx.uow.prompt_versions.get_latest(prompt_type)
        if pv is not None:
            latest.append(pv.model_dump(mode="json"))
    return {"prompts": latest}


async def _view_prompt_execution_log(
    _args: _NoArgs, ctx: ToolContext
) -> dict[str, object]:
    rows = await ctx.uow.prompt_execution_log.list(limit=_LOG_TOOL_LIMIT)
    return {
        "logs": [
            PromptExecutionLogSummary.model_validate(r).model_dump(mode="json")
            for r in rows
        ]
    }


async def _view_prompt_usage_log(_args: _NoArgs, ctx: ToolContext) -> dict[str, object]:
    rows = await ctx.uow.openrouter_usage.list(limit=_LOG_TOOL_LIMIT)
    return {
        "usage": [
            OpenRouterUsageRead.model_validate(r).model_dump(mode="json") for r in rows
        ]
    }


async def _view_ingest_console(_args: _NoArgs, ctx: ToolContext) -> dict[str, object]:
    rows = await ctx.uow.ingest_jobs.list_for_console()
    return {
        "jobs": [
            ConsoleJobRead.model_validate(r).model_dump(mode="json")
            for r in rows[:_LOG_TOOL_LIMIT]
        ]
    }


view_projects_tool = ToolDefinition(
    name="view_projects",
    description="List the construction projects (vergabe id, name, description, "
    "vergabestelle).",
    input_model=_NoArgs,
    handler=_view_projects,
)

view_prompts_tool = ToolDefinition(
    name="view_prompts",
    description="List the latest version of each configured prompt.",
    input_model=_NoArgs,
    handler=_view_prompts,
)

view_prompt_execution_log_tool = ToolDefinition(
    name="view_prompt_execution_log",
    description="List recent prompt execution log entries (LLM calls: model, tokens, "
    "latency, success).",
    input_model=_NoArgs,
    handler=_view_prompt_execution_log,
)

view_prompt_usage_log_tool = ToolDefinition(
    name="view_prompt_usage_log",
    description="List recent OpenRouter usage entries "
    "(operation, model, tokens, cost).",
    input_model=_NoArgs,
    handler=_view_prompt_usage_log,
)

view_ingest_console_tool = ToolDefinition(
    name="view_ingest_console",
    description="List recent document ingestion jobs (file, project, status, attempts, "
    "worker lease).",
    input_model=_NoArgs,
    handler=_view_ingest_console,
)

TOOL_CATALOGS: dict[PromptType, list[ToolDefinition]] = {
    PromptType.DISPATCHER: [
        view_prompts_tool,
        view_projects_tool,
        view_prompt_execution_log_tool,
        view_prompt_usage_log_tool,
        view_ingest_console_tool,
    ],
}


def catalog_for(prompt_type: PromptType) -> list[ToolDefinition]:
    """Tools advertised for a dispatcher prompt type ([] when it isn't a tool-calling
    loop)."""
    return TOOL_CATALOGS.get(prompt_type, [])


def tool_by_name(prompt_type: PromptType, name: str) -> ToolDefinition | None:
    return next((t for t in catalog_for(prompt_type) if t.name == name), None)
