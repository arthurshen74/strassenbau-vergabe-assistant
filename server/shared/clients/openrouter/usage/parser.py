"""Parse the OpenRouter ``usage`` object into a transport-neutral ``UsageEvent``.

Every OpenRouter response (chat, embeddings, rerank) carries a ``usage`` object, but the three
shapes differ: chat has prompt/completion tokens plus cached/reasoning detail, embeddings has
prompt/total tokens, and rerank has neither prompt nor completion tokens but adds ``search_units``.
Every metric is optional in at least one endpoint's schema, so extraction is defensive: an absent
metric becomes ``None``. ``cost`` is OpenRouter credits (== USD), reported as a JSON float and
converted to ``Decimal`` to avoid binary-float drift.

A ``UsageEvent`` is what clients hand to a ``UsageSink``; it is decoupled from persistence (the DB
model is derived from it at the sink).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import UsageOperation

# Top-level response key shared across endpoints.
FIELD_USAGE = "usage"
FIELD_RESPONSE_ID = "id"

# usage object keys.
FIELD_PROMPT_TOKENS = "prompt_tokens"
FIELD_COMPLETION_TOKENS = "completion_tokens"
FIELD_TOTAL_TOKENS = "total_tokens"
FIELD_COST = "cost"
FIELD_SEARCH_UNITS = "search_units"

# Nested detail objects (chat only).
FIELD_PROMPT_TOKENS_DETAILS = "prompt_tokens_details"
FIELD_CACHED_TOKENS = "cached_tokens"
FIELD_COMPLETION_TOKENS_DETAILS = "completion_tokens_details"
FIELD_REASONING_TOKENS = "reasoning_tokens"


class MissingUsageError(ValueError):
    """The response carried no ``usage`` object; nothing to record."""


class MalformedUsageError(ValueError):
    """A present ``usage`` field held a non-numeric value."""


class UsageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: UsageOperation
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: Decimal | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    search_units: int | None = None
    project_uuid: UUID | None = None
    ingest_job_uuid: UUID | None = None
    document_uuid: UUID | None = None
    conversation_uuid: UUID | None = None
    request_id: str | None = None
    chat_prompt_type: str | None = None
    chat_prompt_version: int | None = None


def _as_int(usage: dict[str, Any], key: str) -> int | None:
    value = usage.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedUsageError(f"usage.{key} is not an integer: {value!r}")
    return value


def _as_decimal(usage: dict[str, Any], key: str) -> Decimal | None:
    value = usage.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MalformedUsageError(f"usage.{key} is not a number: {value!r}")
    return Decimal(str(value))


def _nested_int(usage: dict[str, Any], parent: str, key: str) -> int | None:
    details = usage.get(parent)
    if not isinstance(details, dict):
        return None
    return _as_int(details, key)


def parse_usage(
    body: dict[str, Any],
    *,
    operation: UsageOperation,
    model: str,
    project_uuid: UUID | None = None,
    ingest_job_uuid: UUID | None = None,
    document_uuid: UUID | None = None,
    conversation_uuid: UUID | None = None,
    chat_prompt_type: str | None = None,
    chat_prompt_version: int | None = None,
) -> UsageEvent:
    """Extract the ``usage`` object from an OpenRouter response body into a ``UsageEvent``.

    Raises ``MissingUsageError`` when the body has no ``usage`` object and ``MalformedUsageError``
    when a present field is non-numeric; callers wrap this in a guarded emit and skip persistence
    on either error. A missing ``cost`` alone is normal and recorded as ``None``.
    """
    usage = body.get(FIELD_USAGE)
    if not isinstance(usage, dict):
        raise MissingUsageError(f"response for {operation} has no usage object")

    request_id = body.get(FIELD_RESPONSE_ID)
    return UsageEvent(
        operation=operation,
        model=model,
        prompt_tokens=_as_int(usage, FIELD_PROMPT_TOKENS),
        completion_tokens=_as_int(usage, FIELD_COMPLETION_TOKENS),
        total_tokens=_as_int(usage, FIELD_TOTAL_TOKENS),
        cost=_as_decimal(usage, FIELD_COST),
        cached_tokens=_nested_int(usage, FIELD_PROMPT_TOKENS_DETAILS, FIELD_CACHED_TOKENS),
        reasoning_tokens=_nested_int(
            usage, FIELD_COMPLETION_TOKENS_DETAILS, FIELD_REASONING_TOKENS
        ),
        search_units=_as_int(usage, FIELD_SEARCH_UNITS),
        project_uuid=project_uuid,
        ingest_job_uuid=ingest_job_uuid,
        document_uuid=document_uuid,
        conversation_uuid=conversation_uuid,
        request_id=request_id if isinstance(request_id, str) else None,
        chat_prompt_type=chat_prompt_type,
        chat_prompt_version=chat_prompt_version,
    )
