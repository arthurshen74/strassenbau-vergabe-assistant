"""Dispatcher tool catalogs keyed by PromptType.

Mirrors the output-schema registry: the single place that declares which tools each dispatcher
advertises. Handlers call repositories directly via the `ToolContext`. Project-chat tools are
scoped by the conversation's `project_uuid` (taken from context, never from the model) so the
model can't reach another project's data.

`view_lvitems` consolidates "all items for the project" and "items under a parent_oz" into one
tool with an optional `parent_oz` filter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shared.models.enums import PromptType
from shared.models.openrouter_usage_schema import OpenRouterUsageRead
from shared.models.prompt_execution_log_schema import PromptExecutionLogSummary
from shared.tools._base import ToolContext, ToolDefinition

# Rows a log tool surfaces to the dispatcher (recent-first); the UI views page/filter via REST.
_LOG_TOOL_LIMIT = 50


class _NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ViewLvItemsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_oz: str | None = Field(
        default=None,
        description="If set, return only items whose parent is this Ordnungszahl; "
        "otherwise return all items for the project.",
    )


class ViewLvItemArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oz: str = Field(description="The Ordnungszahl (position number) of the LV item.")


class GetContextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="What to retrieve relevant project context for.")


def _require_project(ctx: ToolContext) -> None:
    if ctx.project_uuid is None:
        raise ValueError("this tool requires a project-scoped conversation")


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


async def _view_prompt_execution_log(_args: _NoArgs, ctx: ToolContext) -> dict[str, object]:
    rows = await ctx.uow.prompt_execution_log.list(limit=_LOG_TOOL_LIMIT)
    return {
        "logs": [
            PromptExecutionLogSummary.model_validate(r).model_dump(mode="json") for r in rows
        ]
    }


async def _view_prompt_usage_log(_args: _NoArgs, ctx: ToolContext) -> dict[str, object]:
    rows = await ctx.uow.openrouter_usage.list(limit=_LOG_TOOL_LIMIT)
    return {"usage": [OpenRouterUsageRead.model_validate(r).model_dump(mode="json") for r in rows]}


async def _view_lvitems(args: ViewLvItemsArgs, ctx: ToolContext) -> dict[str, object]:
    _require_project(ctx)
    assert ctx.project_uuid is not None
    if args.parent_oz is not None:
        items = await ctx.uow.lv_items.list_by_parent_oz(ctx.project_uuid, args.parent_oz)
    else:
        items = await ctx.uow.lv_items.list_by_project(ctx.project_uuid)
    return {"lv_items": [i.model_dump(mode="json") for i in items]}


async def _view_lvitem(args: ViewLvItemArgs, ctx: ToolContext) -> dict[str, object]:
    _require_project(ctx)
    assert ctx.project_uuid is not None
    item = await ctx.uow.lv_items.get_by_project_and_oz(ctx.project_uuid, args.oz)
    return {"lv_item": item.model_dump(mode="json") if item else None}


async def _get_context(args: GetContextArgs, ctx: ToolContext) -> dict[str, object]:
    # STUB: real RAG retrieval (multi-query -> embed -> hybrid search -> rerank -> cited
    # chunks) is deferred. Returns empty context so the dispatcher loop still finalizes.
    _require_project(ctx)
    return {"chunks": [], "note": "retrieval not yet implemented"}


view_projects_tool = ToolDefinition(
    name="view_projects",
    description="List the construction projects (vergabe id, name, description, vergabestelle).",
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
    description="List recent prompt execution log entries (LLM calls: model, tokens, latency, success).",
    input_model=_NoArgs,
    handler=_view_prompt_execution_log,
)

view_prompt_usage_log_tool = ToolDefinition(
    name="view_prompt_usage_log",
    description="List recent OpenRouter usage entries (operation, model, tokens, cost).",
    input_model=_NoArgs,
    handler=_view_prompt_usage_log,
)

view_lvitems_tool = ToolDefinition(
    name="view_lvitems",
    description=(
        "List Leistungsverzeichnis items for this project. Optionally filter to the children "
        "of a given parent Ordnungszahl (parent_oz)."
    ),
    input_model=ViewLvItemsArgs,
    handler=_view_lvitems,
)

view_lvitem_tool = ToolDefinition(
    name="view_lvitem",
    description="Show one Leistungsverzeichnis item for this project by its Ordnungszahl (oz).",
    input_model=ViewLvItemArgs,
    handler=_view_lvitem,
)

get_context_tool = ToolDefinition(
    name="get_context",
    description="Retrieve relevant passages from the project's documents for a query.",
    input_model=GetContextArgs,
    handler=_get_context,
)

TOOL_CATALOGS: dict[PromptType, list[ToolDefinition]] = {
    PromptType.DISPATCHER: [
        view_prompts_tool,
        view_projects_tool,
        view_prompt_execution_log_tool,
        view_prompt_usage_log_tool,
    ],
    PromptType.PROJECT_CHAT: [
        view_lvitems_tool,
        view_lvitem_tool,
        get_context_tool,
    ],
}


def catalog_for(prompt_type: PromptType) -> list[ToolDefinition]:
    """Tools advertised for a dispatcher prompt type ([] when it isn't a tool-calling loop)."""
    return TOOL_CATALOGS.get(prompt_type, [])


def tool_by_name(prompt_type: PromptType, name: str) -> ToolDefinition | None:
    return next((t for t in catalog_for(prompt_type) if t.name == name), None)
