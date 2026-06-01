from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from shared.models.enums import MessageKind
from shared.models.message import Message
from shared.services.messages import to_chat_completions_messages


def _m(kind: MessageKind, **kw: Any) -> Message:
    return Message(
        message_uuid=uuid4(),
        conversation_uuid=uuid4(),
        kind=kind,
        created_at=datetime.now(UTC),
        **kw,
    )


def test_coalesces_function_calls_and_replies() -> None:
    rows = [
        _m(MessageKind.USER, content="hi"),
        _m(MessageKind.FUNCTION_CALL, call_id="c1", tool_name="view_projects", arguments={}),
        _m(MessageKind.FUNCTION_CALL, call_id="c2", tool_name="view_lvitem", arguments={"oz": "01"}),
        _m(MessageKind.FUNCTION_CALL_OUTPUT, call_id="c1", tool_name="view_projects", success=True, data={"projects": []}),
        _m(MessageKind.FUNCTION_CALL_OUTPUT, call_id="c2", tool_name="view_lvitem", success=False, errors=["nope"]),
        _m(MessageKind.ASSISTANT, content="done"),
    ]
    out = to_chat_completions_messages(rows)

    assert out[0] == {"role": "user", "content": "hi"}

    envelope = out[1]
    assert envelope["role"] == "assistant"
    assert envelope["content"] is None
    assert [tc["function"]["name"] for tc in envelope["tool_calls"]] == [
        "view_projects",
        "view_lvitem",
    ]
    assert envelope["tool_calls"][1]["function"]["arguments"] == '{"oz": "01"}'

    assert out[2]["role"] == "tool" and out[2]["tool_call_id"] == "c1"
    assert json.loads(out[2]["content"]) == {"success": True, "data": {"projects": []}}
    assert out[3]["role"] == "tool" and out[3]["tool_call_id"] == "c2"
    assert json.loads(out[3]["content"]) == {"success": False, "errors": ["nope"]}

    assert out[4] == {"role": "assistant", "content": "done"}


def test_empty_history_is_empty() -> None:
    assert to_chat_completions_messages([]) == []
