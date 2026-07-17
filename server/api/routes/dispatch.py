from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.deps import Principal, get_current_user, get_dispatcher
from api.sse import SSE_MEDIA_TYPE, format_sse
from shared.models.sse_schema import (
    DATA,
    DATA_CONTENT,
    DATA_LEVEL,
    EVENT,
    EVENT_DONE,
    EVENT_UI_NOTICE,
    NOTICE_PROCESSING_ERROR,
    NoticeLevel,
)
from shared.services.dispatcher import Dispatcher
from shared.services.security import InputRejectedError, guard_user_input

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


class DispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)


@router.post("")
async def dispatch(
    payload: DispatchRequest,
    principal: Principal = Depends(get_current_user),
    dispatcher: Dispatcher = Depends(get_dispatcher),
) -> StreamingResponse:
    """Single-shot command routing: no conversation, no persistence. Streams the same
    SSE envelopes as a chat turn; the UI opens the resulting view tool in its main
    window."""
    try:
        guard_user_input(payload.content)
    except InputRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    events = dispatcher.dispatch(payload.content)

    async def event_stream() -> AsyncIterator[str]:
        # The 200 + headers are already committed once streaming starts, so an exception
        # here cannot become an HTTP error. Surface it as a ui_notice + done instead of
        # letting the connection close silently, and log the cause server-side.
        try:
            async for event in events:
                yield format_sse(event)
        except Exception:
            logger.exception("dispatch stream failed")
            yield format_sse(
                {
                    EVENT: EVENT_UI_NOTICE,
                    DATA: {
                        DATA_CONTENT: NOTICE_PROCESSING_ERROR,
                        DATA_LEVEL: NoticeLevel.ERROR,
                    },
                }
            )
            yield format_sse({EVENT: EVENT_DONE, DATA: {}})

    return StreamingResponse(event_stream(), media_type=SSE_MEDIA_TYPE)
