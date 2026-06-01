from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from shared.clients.openrouter.usage import (
    MalformedUsageError,
    MissingUsageError,
    parse_usage,
)
from shared.models.enums import UsageOperation


def test_parse_chat_usage_full() -> None:
    body = {
        "id": "gen-abc",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "cost": 0.0021,
            "prompt_tokens_details": {"cached_tokens": 64},
            "completion_tokens_details": {"reasoning_tokens": 12},
        },
    }
    event = parse_usage(body, operation=UsageOperation.CHAT, model="anthropic/claude-sonnet-4.6")

    assert event.operation is UsageOperation.CHAT
    assert event.prompt_tokens == 100
    assert event.completion_tokens == 40
    assert event.total_tokens == 140
    assert event.cost == Decimal("0.0021")
    assert event.cached_tokens == 64
    assert event.reasoning_tokens == 12
    assert event.search_units is None
    assert event.request_id == "gen-abc"


def test_parse_embeddings_usage_no_completion() -> None:
    body = {"usage": {"prompt_tokens": 8, "total_tokens": 8, "cost": 0.0000004}}
    event = parse_usage(
        body, operation=UsageOperation.EMBEDDING, model="openai/text-embedding-3-small"
    )

    assert event.prompt_tokens == 8
    assert event.completion_tokens is None
    assert event.total_tokens == 8
    assert event.cost == Decimal("0.0000004")
    assert event.search_units is None
    assert event.request_id is None


def test_parse_rerank_usage_search_units_no_tokens() -> None:
    body = {
        "id": "orid-1",
        "usage": {"total_tokens": 0, "search_units": 1, "cost": 0.002},
    }
    event = parse_usage(body, operation=UsageOperation.RERANK, model="cohere/rerank-v3.5")

    assert event.prompt_tokens is None
    assert event.completion_tokens is None
    assert event.total_tokens == 0
    assert event.search_units == 1
    assert event.cost == Decimal("0.002")
    assert event.request_id == "orid-1"


def test_cost_omitted_is_none() -> None:
    body = {"usage": {"prompt_tokens": 5, "total_tokens": 5}}
    event = parse_usage(
        body, operation=UsageOperation.EMBEDDING, model="openai/text-embedding-3-small"
    )
    assert event.cost is None


def test_missing_usage_raises() -> None:
    with pytest.raises(MissingUsageError):
        parse_usage({"id": "x"}, operation=UsageOperation.CHAT, model="m")


def test_non_numeric_field_raises() -> None:
    body = {"usage": {"prompt_tokens": "lots", "total_tokens": 5}}
    with pytest.raises(MalformedUsageError):
        parse_usage(body, operation=UsageOperation.EMBEDDING, model="m")


def test_cost_float_to_exact_decimal() -> None:
    # 0.1 is not exactly representable in binary float; Decimal(str(x)) keeps the decimal text.
    body = {"usage": {"total_tokens": 1, "cost": 0.1}}
    event = parse_usage(body, operation=UsageOperation.RERANK, model="m")
    assert event.cost == Decimal("0.1")


def test_attribution_and_prompt_fields_flow_through() -> None:
    project_uuid = uuid4()
    ingest_job_uuid = uuid4()
    body = {"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0}}
    event = parse_usage(
        body,
        operation=UsageOperation.CHAT,
        model="m",
        project_uuid=project_uuid,
        ingest_job_uuid=ingest_job_uuid,
        chat_prompt_type="project_chat",
        chat_prompt_version=3,
    )
    assert event.project_uuid == project_uuid
    assert event.ingest_job_uuid == ingest_job_uuid
    assert event.chat_prompt_type == "project_chat"
    assert event.chat_prompt_version == 3
