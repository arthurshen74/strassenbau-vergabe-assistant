from __future__ import annotations

from shared.models.enums import PromptType
from shared.tools import catalog_for, tool_by_name


def test_catalogs_per_prompt_type() -> None:
    assert [t.name for t in catalog_for(PromptType.DISPATCHER)] == [
        "view_prompts",
        "view_projects",
        "view_prompt_execution_log",
        "view_prompt_usage_log",
    ]


def test_non_dispatcher_prompt_types_have_no_tools() -> None:
    # Project chat runs ProjectChatService, not the dispatcher tool-loop.
    assert catalog_for(PromptType.PROJECT_CHAT) == []
    assert catalog_for(PromptType.MULTI_QUESTION_GENERATOR) == []


def test_tool_by_name() -> None:
    assert tool_by_name(PromptType.DISPATCHER, "view_projects") is not None
    assert tool_by_name(PromptType.DISPATCHER, "view_lvitem") is None


def test_to_openai_tool_shape() -> None:
    tool = tool_by_name(PromptType.DISPATCHER, "view_projects")
    assert tool is not None
    rendered = tool.to_openai_tool()
    assert rendered["type"] == "function"
    assert rendered["function"]["name"] == "view_projects"
    assert "properties" in rendered["function"]["parameters"]
