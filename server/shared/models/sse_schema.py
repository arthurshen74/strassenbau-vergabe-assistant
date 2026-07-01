"""SSE event payloads streamed by the dispatcher to the UI.

`run_turn` yields envelopes shaped `{event: <name>, data: {...}}`; the SSE writer renders them
and the frontend spreads the payload to the top level (`{event, ...data}`). The flat models below
mirror that flattened client view and form the `SSEEvent` discriminated union that
scripts/export_schema.py emits.

The `EVENT_*` / `DATA_*` constants are the single source of truth for the wire discriminators and
payload keys; the dispatcher imports them rather than re-typing the literals.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# SSE envelope keys.
EVENT = "event"
DATA = "data"

# Event names (the `event:` discriminator).
EVENT_TEXT_DELTA = "text_delta"
EVENT_FUNCTION_CALL = "function_call"
EVENT_FUNCTION_CALL_OUTPUT = "function_call_output"
EVENT_UI_NOTICE = "ui_notice"
EVENT_INTERRUPT = "interrupt"
EVENT_CALC_START = "calc_start"
EVENT_DONE = "done"

# Event-data payload keys.
DATA_CALL_ID = "call_id"
DATA_NAME = "name"
DATA_ARGUMENTS = "arguments"
DATA_TOOL_NAME = "tool_name"
DATA_SUCCESS = "success"
DATA_RESULT = "data"
DATA_ERRORS = "errors"
DATA_CONTENT = "content"
DATA_LEVEL = "level"
DATA_STAGE = "stage"
DATA_PAYLOAD = "payload"


class NoticeLevel(StrEnum):
    """Severity of a ui_notice; drives whether the UI renders it muted or error-styled."""

    INFO = "info"
    ERROR = "error"


# User-facing copy for a turn that failed before or during streaming. Shared by the project-chat
# service and the streaming routes so the message reads the same wherever a turn breaks.
NOTICE_PROCESSING_ERROR = (
    "Sorry, something went wrong while processing your message. Please try again."
)


class SSETextDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["text_delta"]
    content: str


class SSEFunctionCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["function_call"]
    call_id: str
    name: str
    arguments: dict[str, Any]


class SSEFunctionCallOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["function_call_output"]
    call_id: str
    tool_name: str
    success: bool
    data: dict[str, Any] | None = None
    errors: list[str] | None = None


class SSEUiNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["ui_notice"]
    content: str
    level: NoticeLevel = NoticeLevel.INFO


class SSEInterrupt(BaseModel):
    """A HITL pause in the EKT calculator run: the UI renders a control for `stage` and posts the
    decision to the calculation resume endpoint. `payload` is the interrupt value from the graph."""

    model_config = ConfigDict(extra="forbid")

    event: Literal["interrupt"]
    stage: str
    payload: dict[str, Any]


class SSECalcStart(BaseModel):
    """A calculation segment has begun streaming reasoning. Lets the UI switch the open turn into
    calculator mode (collapse the reasoning to its latest line, show the activity indicator) even
    when the segment was chained from a position-chat message rather than a HITL resume."""

    model_config = ConfigDict(extra="forbid")

    event: Literal["calc_start"]


class SSEDone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["done"]


SSEEvent = Annotated[
    SSETextDelta
    | SSEFunctionCall
    | SSEFunctionCallOutput
    | SSEUiNotice
    | SSEInterrupt
    | SSECalcStart
    | SSEDone,
    Field(discriminator="event"),
]
