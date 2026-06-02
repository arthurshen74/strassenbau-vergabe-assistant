from __future__ import annotations

import pytest

from shared.clients.factory import (
    build_embeddings_client,
    build_llm_client,
    build_rerank_client,
    build_telemetry_sinks,
)
from shared.clients.llm.execution_log_sinks import DatabaseExecutionLogSink
from shared.clients.openrouter.usage import DatabaseUsageSink

# httpx reads proxy env vars when constructing a default client; a SOCKS proxy in the ambient
# environment would otherwise break client construction here (and pull in socksio).
_PROXY_ENV_VARS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "ftp_proxy",
)


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _PROXY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


class _StubEngine:
    """Stands in for an AsyncEngine; the sinks only hold it, never touch it here."""


def test_build_telemetry_sinks_wraps_the_engine() -> None:
    engine = _StubEngine()
    sinks = build_telemetry_sinks(engine)

    assert isinstance(sinks.usage, DatabaseUsageSink)
    assert isinstance(sinks.execution_log, DatabaseExecutionLogSink)
    assert sinks.usage._engine is engine
    assert sinks.execution_log._engine is engine


def test_clients_share_one_usage_sink_and_execution_log_sink() -> None:
    sinks = build_telemetry_sinks(_StubEngine())

    llm = build_llm_client(sinks)
    embeddings = build_embeddings_client(sinks)
    rerank = build_rerank_client(sinks)

    assert llm._usage_sink is sinks.usage
    assert embeddings._usage_sink is sinks.usage
    assert rerank._usage_sink is sinks.usage
    assert llm._execution_log_sink is sinks.execution_log
