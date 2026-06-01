from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MultiQueryRewrite(BaseModel):
    """Structured output for the retrieval multi-query generator: a list of query variants."""

    model_config = ConfigDict(extra="forbid")

    queries: list[str] = Field(description="Reworded variants of the user's query.")
