"""The astream_events -> SSE mapping for the project-chat agent.

`map_agent_event` turns one LangChain astream_events v2 event into an AgentEvent (or None). The
run_id pairs a tool call with its result, so a call and its output share a call_id even when several
tools run in one assistant turn."""

from __future__ import annotations

from types import SimpleNamespace

from shared.services.project_chat_agent import (
    AgentToken,
    AgentToolCall,
    AgentToolResult,
    map_agent_event,
)


def test_maps_chat_token() -> None:
    event = {"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="Hi")}}
    out = map_agent_event(event)
    assert isinstance(out, AgentToken)
    assert out.content == "Hi"


def test_empty_token_is_dropped() -> None:
    event = {"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="")}}
    assert map_agent_event(event) is None


def test_maps_tool_call_carrying_run_id_and_args() -> None:
    event = {
        "event": "on_tool_start",
        "name": "get_project_context",
        "run_id": "run-1",
        "data": {"input": {"query": "ZTV Asphalt"}},
    }
    out = map_agent_event(event)
    assert isinstance(out, AgentToolCall)
    assert out.call_id == "run-1"
    assert out.name == "get_project_context"
    assert out.arguments == {"query": "ZTV Asphalt"}


def test_maps_tool_result_pairs_same_run_id() -> None:
    event = {
        "event": "on_tool_end",
        "name": "aggregate_lv_items",
        "run_id": "run-1",
        "data": {"output": SimpleNamespace(artifact={"per_unit": []})},
    }
    out = map_agent_event(event)
    assert isinstance(out, AgentToolResult)
    assert out.call_id == "run-1"
    assert out.name == "aggregate_lv_items"
    assert out.payload == {"per_unit": []}


def test_tool_result_without_artifact_is_empty_payload() -> None:
    event = {
        "event": "on_tool_end",
        "name": "get_lv_all",
        "run_id": "r",
        "data": {"output": SimpleNamespace()},
    }
    out = map_agent_event(event)
    assert isinstance(out, AgentToolResult)
    assert out.payload == {}


def test_unrelated_event_is_dropped() -> None:
    assert map_agent_event({"event": "on_chain_start", "data": {}}) is None
