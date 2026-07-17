"""Phoenix (OpenTelemetry) tracing bootstrap.

`setup_phoenix_tracing` points the OTLP exporter at the Phoenix collector from settings
and auto-instruments every LangChain/LangGraph run in the process, so graph nodes, LLM
calls and tool invocations appear as nested spans in the Phoenix UI under
`project_name`. Call it once at process start (CLI entrypoints, worker main, API
lifespan); it is global, not per-request.

`flow_span` opens a per-flow root span. It is load-bearing, not cosmetic: openinference
parents its node/tool spans via LangChain's run-tree and never attaches them to the OTel
context, so a non-LangChain span (our LLMClient OTel sink span, elasticsearch-py's
native query spans) created inside a node/tool body cannot see that node/tool as its
parent and would otherwise orphan into its own root trace. Wrapping a flow's execution
in `flow_span` makes the ambient context non-empty, so those spans and the auto
LangChain/LangGraph spans all collapse into one trace per flow run. It is also where
`session.id` is set, grouping a conversation's turns into one Phoenix session.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from typing import Any

from openinference.instrumentation import using_session
from openinference.instrumentation.langchain._tracer import OpenInferenceTracer
from openinference.semconv.trace import SpanAttributes
from opentelemetry import trace
from opentelemetry.trace import Span
from phoenix.otel import register

from shared.config import settings

_TRACER_NAME = "roadbuilders"
# ProxyTracer: resolves the real provider lazily at span-creation time, so acquiring it
# at import (before setup_phoenix_tracing runs register()) is safe.
_tracer = trace.get_tracer(_TRACER_NAME)

# register() sets the global TracerProvider and instruments; calling it twice
# re-registers. Guard so repeated create_app()/imports/tests install tracing once per
# process.
_tracing_installed = False


def _noop(self: object, *args: object, **kwargs: object) -> None:
    return None


def setup_phoenix_tracing(project_name: str) -> None:
    global _tracing_installed
    if _tracing_installed:
        return
    # langgraph dispatches on_interrupt/on_resume to every callback handler;
    # openinference 0.1.x predates these events and logs an AttributeError per
    # interrupt. No-op them until the instrumentor catches up.
    for name in ("on_interrupt", "on_resume"):
        if not hasattr(OpenInferenceTracer, name):
            setattr(OpenInferenceTracer, name, _noop)
    register(
        endpoint=settings.phoenix_collector_endpoint,
        project_name=project_name,
        auto_instrument=True,
        # BatchSpanProcessor: export off the request path, so a slow/unreachable
        # collector never adds latency to a turn (the default SimpleSpanProcessor
        # exports synchronously on span end).
        batch=True,
    )
    _tracing_installed = True


@contextmanager
def flow_span(
    name: str,
    *,
    session_id: str | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[Span]:
    """Open a per-flow root span; see module docstring for why it is required for
    nesting.

    `session_id` (a conversation_uuid) groups the trace into a Phoenix session: it is
    stamped on this span and, via `using_session`, on the auto LangChain/LangGraph child
    spans.
    """
    session_cm = using_session(session_id) if session_id is not None else nullcontext()
    with session_cm, _tracer.start_as_current_span(name) as span:
        if session_id is not None:
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        yield span
