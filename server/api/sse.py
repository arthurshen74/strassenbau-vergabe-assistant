"""Server-Sent Events formatting for streaming endpoints."""

from __future__ import annotations

import json
from typing import Any

EVENT = "event"
DATA = "data"

SSE_MEDIA_TYPE = "text/event-stream"

# A comment line keeps the connection alive without emitting an event (ignored by
# clients).
SSE_HEARTBEAT = ": ping\n\n"


def format_sse(event: dict[str, Any]) -> str:
    """Format a `{"event": name, "data": {...}}` payload as one SSE message."""
    name = event[EVENT]
    payload = json.dumps(event.get(DATA, {}))
    return f"event: {name}\ndata: {payload}\n\n"
