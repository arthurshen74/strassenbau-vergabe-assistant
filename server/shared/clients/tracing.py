"""Phoenix (OpenTelemetry) tracing bootstrap.

`setup_phoenix_tracing` points the OTLP exporter at the Phoenix collector from settings and
auto-instruments every LangChain/LangGraph run in the process, so graph nodes, LLM calls and
tool invocations appear as nested spans in the Phoenix UI under `project_name`. Call it once
at process start (CLI entrypoints, worker main); it is global, not per-request.
"""

from __future__ import annotations

from openinference.instrumentation.langchain._tracer import OpenInferenceTracer
from phoenix.otel import register

from shared.config import settings


def _noop(self: object, *args: object, **kwargs: object) -> None:
    return None


def setup_phoenix_tracing(project_name: str) -> None:
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
    )
