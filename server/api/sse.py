"""Server-Sent Events formatting for streaming endpoints."""

from __future__ import annotations

import json
from typing import Any

EVENT = "event"
DATA = "data"


def format_sse(event: dict[str, Any]) -> str:
    """Format a `{"event": name, "data": {...}}` payload as one SSE message."""
    name = event[EVENT]
    payload = json.dumps(event.get(DATA, {}))
    return f"event: {name}\ndata: {payload}\n\n"
