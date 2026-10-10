"""Retrieval policy for the project-info queries.

Mirrors the project-context resolver's hybrid policy (RESOLVE_RETRIEVAL_CONFIG) under
its own name so either can be tuned without touching the other.
"""

from __future__ import annotations

from shared.models.enums import RetrievalModality
from shared.services.retrieval.config import RetrievalConfig

PROJECT_INFO_RETRIEVAL_CONFIG = RetrievalConfig(
    modality=RetrievalModality.PLUS,
    multi_query=True,
    use_bm25=True,
    use_cross_encoder=True,
)
