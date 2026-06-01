"""Rebuild OpenAI chat-completions messages from stored conversation rows.

Also the single source of truth for the chat-completions message wire format (roles, the
assistant `tool_calls` envelope, and `role:"tool"` replies), shared with the dispatcher so the
live loop and the rebuilt history are constructed the same way.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from shared.models.enums import MessageKind
from shared.models.message import Message

# Chat-completions message keys and roles.
ROLE = "role"
CONTENT = "content"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"

# Assistant tool_calls envelope + tool reply keys.
TOOL_CALLS = "tool_calls"
TOOL_CALL_ID_FIELD = "id"
TOOL_CALL_TYPE = "type"
TOOL_CALL_TYPE_FUNCTION = "function"
FUNCTION = "function"
FUNCTION_NAME = "name"
FUNCTION_ARGUMENTS = "arguments"
TOOL_CALL_ID = "tool_call_id"

# Keys inside a serialized tool-result payload (the `content` of a tool reply).
OUTPUT_SUCCESS = "success"
OUTPUT_DATA = "data"
OUTPUT_ERRORS = "errors"


def user_message(content: str) -> dict[str, Any]:
    return {ROLE: ROLE_USER, CONTENT: content}


def assistant_message(content: str) -> dict[str, Any]:
    return {ROLE: ROLE_ASSISTANT, CONTENT: content}


def tool_call_entry(call_id: str, tool_name: str, arguments_json: str) -> dict[str, Any]:
    return {
        TOOL_CALL_ID_FIELD: call_id,
        TOOL_CALL_TYPE: TOOL_CALL_TYPE_FUNCTION,
        FUNCTION: {FUNCTION_NAME: tool_name, FUNCTION_ARGUMENTS: arguments_json},
    }


def assistant_tool_calls_message(calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {ROLE: ROLE_ASSISTANT, CONTENT: None, TOOL_CALLS: calls}


def tool_result_payload(
    success: bool, data: dict[str, Any] | None, errors: list[str] | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {OUTPUT_SUCCESS: success}
    if data is not None:
        payload[OUTPUT_DATA] = data
    if errors:
        payload[OUTPUT_ERRORS] = errors
    return payload


def tool_reply_message(call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {ROLE: ROLE_TOOL, TOOL_CALL_ID: call_id, CONTENT: json.dumps(payload)}


def to_chat_completions_messages(stored: Sequence[Message]) -> list[dict[str, Any]]:
    """Coalesce stored rows into the chat-completions list, merging consecutive function_call
    rows into one assistant tool_calls envelope followed by their tool replies."""
    out: list[dict[str, Any]] = []
    i = 0
    n = len(stored)
    while i < n:
        m = stored[i]
        if m.kind == MessageKind.USER:
            out.append(user_message(m.content or ""))
            i += 1
        elif m.kind == MessageKind.ASSISTANT:
            out.append(assistant_message(m.content or ""))
            i += 1
        elif m.kind == MessageKind.FUNCTION_CALL:
            calls: list[dict[str, Any]] = []
            while i < n and stored[i].kind == MessageKind.FUNCTION_CALL:
                fc = stored[i]
                assert fc.call_id is not None and fc.tool_name is not None
                calls.append(
                    tool_call_entry(fc.call_id, fc.tool_name, json.dumps(fc.arguments or {}))
                )
                i += 1
            out.append(assistant_tool_calls_message(calls))
        else:  # FUNCTION_CALL_OUTPUT
            assert m.call_id is not None
            payload = tool_result_payload(bool(m.success), m.data, m.errors)
            out.append(tool_reply_message(m.call_id, payload))
            i += 1
    return out
