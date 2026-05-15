"""Common LLM call wrapper, built on Anthropic's structured-outputs API.

Each call passes a Pydantic class as `output_format=`; the SDK returns a
validated, typed instance on `response.parsed_output`. Schema-compliant
output is guaranteed by the API except for two stop_reasons that this
module surfaces as explicit exceptions:

- stop_reason == "refusal"     -> RefusalError
- stop_reason == "max_tokens"  -> OutputTruncatedError

The system prompt is always sent as a single text block with
`cache_control: ephemeral` so repeated calls within a phase pay the
cheap cache-read price after the first call. When the system prompt is
below the model's minimum cacheable prefix (2048 tok on Sonnet 4.6,
4096 tok on Opus 4.x), the API silently no-ops — no extra cost.

Per-call usage (input / output / cache_creation / cache_read tokens) is
accumulated on the client; expose totals via `usage_summary()`.

Retries with exponential backoff + equal jitter on anthropic.APIError /
RateLimitError. Optional per-model fallback: pass models as a sequence
to try each in order on APIError exhaustion.
"""

from __future__ import annotations

import random
import sys
import time
from typing import Sequence, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class RefusalError(RuntimeError):
    """The model refused the request. response.stop_reason == 'refusal'."""


class OutputTruncatedError(RuntimeError):
    """The response was cut off at max_tokens before the schema completed."""


class LLMClient:
    def __init__(
        self,
        anthropic_client: anthropic.Anthropic,
        *,
        max_attempts: int = 8,
        base_delay: float = 1.0,
        max_delay: float = 120.0,
    ) -> None:
        self._client = anthropic_client
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._input_tokens = 0
        self._output_tokens = 0
        self._cache_creation_tokens = 0
        self._cache_read_tokens = 0

    def usage_summary(self) -> dict[str, int]:
        return {
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "cache_creation_input_tokens": self._cache_creation_tokens,
            "cache_read_input_tokens": self._cache_read_tokens,
        }

    def _call_with_retry(self, fn, *, what: str):
        last_exc: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                return fn()
            except (anthropic.APIError, anthropic.RateLimitError) as exc:
                last_exc = exc
                if attempt == self._max_attempts - 1:
                    break
                base = min(self._max_delay, self._base_delay * (2 ** attempt))
                delay = base / 2 + random.uniform(0, base / 2)
                print(
                    f"  retry {attempt + 1}/{self._max_attempts} for {what} "
                    f"in {delay:.1f}s: {exc}",
                    file=sys.stderr,
                )
                time.sleep(delay)
        raise RuntimeError(
            f"giving up on {what} after {self._max_attempts} attempts: {last_exc}"
        )

    def call(
        self,
        *,
        models: str | Sequence[str],
        system: str,
        user_content: str | list[dict],
        output_model: type[T],
        max_tokens: int,
        temperature: float = 0.0,
        stop_sequences: list[str] | None = None,
        where: str,
    ) -> tuple[T, float, str]:
        """Call messages.parse with a Pydantic schema, return typed result.

        Returns (parsed_instance, elapsed_seconds, model_used).

        - Refusals and max_tokens truncation raise RefusalError /
          OutputTruncatedError on the *current* model — they do not advance
          to the next model in the fallback list.
        - APIError exhaustion advances to the next model in the list.
        """
        model_list: list[str] = (
            [models] if isinstance(models, str) else list(models)
        )
        if not model_list:
            raise ValueError("at least one model must be provided")

        messages = [{"role": "user", "content": user_content}]
        system_blocks = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        kwargs: dict = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_blocks,
            "messages": messages,
            "output_format": output_model,
        }
        if stop_sequences:
            kwargs["stop_sequences"] = list(stop_sequences)

        last_exc: Exception | None = None
        for idx, model in enumerate(model_list):
            try:
                t0 = time.perf_counter()
                response = self._call_with_retry(
                    lambda model=model: self._client.messages.parse(
                        model=model, **kwargs
                    ),
                    what=f"{where} ({model})",
                )
                elapsed = time.perf_counter() - t0

                stop_reason = getattr(response, "stop_reason", None)
                if stop_reason == "refusal":
                    raise RefusalError(
                        f"{where}: model {model} refused the request"
                    )
                if stop_reason == "max_tokens":
                    raise OutputTruncatedError(
                        f"{where}: model {model} hit max_tokens={max_tokens} "
                        f"before completing the schema"
                    )

                parsed = response.parsed_output
                if parsed is None:
                    raise RuntimeError(
                        f"{where}: model {model} returned no parsed_output "
                        f"(stop_reason={stop_reason!r})"
                    )

                usage = getattr(response, "usage", None)
                if usage is not None:
                    self._input_tokens += getattr(usage, "input_tokens", 0) or 0
                    self._output_tokens += getattr(usage, "output_tokens", 0) or 0
                    self._cache_creation_tokens += (
                        getattr(usage, "cache_creation_input_tokens", 0) or 0
                    )
                    self._cache_read_tokens += (
                        getattr(usage, "cache_read_input_tokens", 0) or 0
                    )

                if idx > 0:
                    print(
                        f"  {where}: succeeded on fallback model {model}",
                        file=sys.stderr,
                    )
                return parsed, elapsed, model
            except (anthropic.APIError, RuntimeError) as exc:
                if isinstance(exc, (RefusalError, OutputTruncatedError)):
                    raise
                last_exc = exc
                if idx < len(model_list) - 1:
                    print(
                        f"  {where}: model {model} failed ({exc}); "
                        f"falling back to {model_list[idx + 1]}",
                        file=sys.stderr,
                    )
        raise RuntimeError(
            f"all models exhausted for {where}: {last_exc}"
        )
