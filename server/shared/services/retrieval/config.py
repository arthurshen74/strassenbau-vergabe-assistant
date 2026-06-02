"""Retrieval run configuration.

One RetrievalConfig describes a single retrieval: the scope modality and which optional
stages are enabled (multi-query, BM25 lexical search, cross-encoder rerank), plus the
pool/result sizes. Every stage is opt-in; the size knobs default to the `settings.*`
values so a bare RetrievalConfig() is the documented baseline.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shared.config import settings
from shared.models.enums import RetrievalModality


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modality: RetrievalModality = RetrievalModality.SIMPLE
    multi_query: bool = False
    use_bm25: bool = False
    use_cross_encoder: bool = False
    candidate_k: int = Field(default_factory=lambda: settings.retriever_candidate_k)
    top_k: int = Field(default_factory=lambda: settings.retriever_top_k)
    multi_query_n: int = Field(default_factory=lambda: settings.multi_query_n)
