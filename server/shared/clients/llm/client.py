"""Single OpenRouter transport for every LLM call in the system.

All chat / structured-output traffic goes through `LLMClient`, which targets the OpenRouter
chat-completions endpoint over `httpx`. Callers pass a model slug and, optionally, a Pydantic
output model; with one, the response is JSON-schema-constrained and validated before return.
The two failure modes callers must distinguish are surfaced as `RefusalError` (the model
declined) and `OutputTruncatedError` (the model hit the token limit).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar, overload

import httpx
from pydantic import BaseModel

from shared.config import settings
from shared.models.chat_message import ChatMessage
from shared.models.llm_output_schemas.multi_query import MultiQueryRewrite

logger = logging.getLogger(__name__)

# OpenRouter / OpenAI chat-completions request keys.
REQUEST_MODEL = "model"
REQUEST_MESSAGES = "messages"
REQUEST_TEMPERATURE = "temperature"
REQUEST_TOP_P = "top_p"
REQUEST_MAX_TOKENS = "max_tokens"
REQUEST_RESPONSE_FORMAT = "response_format"

# response_format / json_schema sub-object keys and the response_format discriminator value.
RESPONSE_FORMAT_TYPE = "type"
RESPONSE_FORMAT_JSON_SCHEMA = "json_schema"
JSON_SCHEMA_NAME = "name"
JSON_SCHEMA_STRICT = "strict"
JSON_SCHEMA_SCHEMA = "schema"

# Message object keys and roles.
MESSAGE_ROLE = "role"
MESSAGE_CONTENT = "content"
MESSAGE_REFUSAL = "refusal"
ROLE_SYSTEM = "system"
ROLE_USER = "user"

# Response object keys.
RESPONSE_CHOICES = "choices"
RESPONSE_MESSAGE = "message"
RESPONSE_FINISH_REASON = "finish_reason"

# finish_reason discriminator values that map to the two caller-visible failure modes.
FINISH_REASON_LENGTH = "length"
FINISH_REASON_CONTENT_FILTER = "content_filter"

DEFAULT_TIMEOUT = 60.0

MULTI_QUERY_SYSTEM_PROMPT = (
    "You rewrite a search query into {n} diverse alternative phrasings that a retrieval system "
    "can use to find relevant passages. Preserve the original intent while varying wording, "
    "specificity, and synonyms. Return exactly {n} variants."
)

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base class for LLM transport failures callers may want to distinguish."""


class RefusalError(LLMError):
    """The model declined to answer (refusal field set, or the response was content-filtered)."""


class OutputTruncatedError(LLMError):
    """The model stopped at the token limit (finish_reason=length); the output is incomplete."""


class LLMClient:
    """OpenRouter chat / structured-output transport built on a shared `httpx.AsyncClient`."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        chat_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self._chat_url = chat_url or settings.openrouter_api_url_chat
        self._owns_client = client is None
        self._client = client if client is not None else httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @overload
    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        output_model: None = ...,
        temperature: float = ...,
        top_p: float | None = ...,
        max_tokens: int | None = ...,
    ) -> str: ...

    @overload
    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        output_model: type[T],
        temperature: float = ...,
        top_p: float | None = ...,
        max_tokens: int | None = ...,
    ) -> T: ...

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        output_model: type[T] | None = None,
        temperature: float = 0.0,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> str | T:
        """Run a chat completion. With `output_model`, request JSON-schema-constrained output
        and return a validated instance; without it, return the raw assistant text."""
        payload: dict[str, Any] = {
            REQUEST_MODEL: model,
            REQUEST_MESSAGES: [_serialize_message(m) for m in messages],
            REQUEST_TEMPERATURE: temperature,
        }
        if top_p is not None:
            payload[REQUEST_TOP_P] = top_p
        if max_tokens is not None:
            payload[REQUEST_MAX_TOKENS] = max_tokens
        if output_model is not None:
            payload[REQUEST_RESPONSE_FORMAT] = _json_schema_response_format(output_model)

        response = await self._client.post(self._chat_url, headers=self._headers(), json=payload)
        response.raise_for_status()
        choice = response.json()[RESPONSE_CHOICES][0]
        message = choice[RESPONSE_MESSAGE]
        finish_reason = choice.get(RESPONSE_FINISH_REASON)

        refusal = message.get(MESSAGE_REFUSAL)
        if refusal or finish_reason == FINISH_REASON_CONTENT_FILTER:
            logger.warning("LLM refused: model=%s finish_reason=%s", model, finish_reason)
            raise RefusalError(refusal or "content filtered")
        if finish_reason == FINISH_REASON_LENGTH:
            logger.warning("LLM output truncated: model=%s", model)
            raise OutputTruncatedError(f"output truncated (finish_reason={finish_reason})")

        content = message.get(MESSAGE_CONTENT) or ""
        if output_model is None:
            return content
        return output_model.model_validate_json(content)

    async def multi_query(
        self, query: str, *, model: str | None = None, n: int | None = None
    ) -> list[str]:
        """Generate `n` query variants for retrieval (defaults from settings); return them as strings."""
        model = model or settings.multi_query_model
        n = n if n is not None else settings.multi_query_n
        messages: list[Mapping[str, Any]] = [
            {MESSAGE_ROLE: ROLE_SYSTEM, MESSAGE_CONTENT: MULTI_QUERY_SYSTEM_PROMPT.format(n=n)},
            {MESSAGE_ROLE: ROLE_USER, MESSAGE_CONTENT: query},
        ]
        result = await self.chat(model=model, messages=messages, output_model=MultiQueryRewrite)
        return result.queries[:n]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}


def _serialize_message(message: ChatMessage | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(message, BaseModel):
        return message.model_dump()
    return dict(message)


def _json_schema_response_format(output_model: type[BaseModel]) -> dict[str, Any]:
    return {
        RESPONSE_FORMAT_TYPE: RESPONSE_FORMAT_JSON_SCHEMA,
        RESPONSE_FORMAT_JSON_SCHEMA: {
            JSON_SCHEMA_NAME: output_model.__name__,
            JSON_SCHEMA_STRICT: True,
            JSON_SCHEMA_SCHEMA: output_model.model_json_schema(),
        },
    }
