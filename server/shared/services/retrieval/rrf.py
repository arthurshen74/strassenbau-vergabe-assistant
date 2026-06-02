"""Reciprocal rank fusion over the per-query ranked lists from Elasticsearch.

Fuses the dense and lexical result lists (one per query variant) into a single
ranking. Deduplicates by chunk_uuid while retaining the SimpleChunk itself, so the
downstream rerank and answer stages keep the full chunk. A single input list is a
monotonic pass-through, since 1/(k+rank) strictly decreases with rank (RETRIEVAL.md).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.clients.search import ScoredChunk
from shared.models.simple_chunk import SimpleChunk

# Standard reciprocal-rank-fusion damping constant.
RRF_K = 60


class FusedChunk(BaseModel):
    """A chunk's fused score plus the rank it held in each list that surfaced it."""

    model_config = ConfigDict(extra="forbid")

    chunk: SimpleChunk
    rrf_score: float
    contributing_ranks: dict[str, int]


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[ScoredChunk]],
    *,
    k: int = RRF_K,
    top_n: int | None = None,
) -> list[FusedChunk]:
    """Fuse labelled ranked lists into one ranking by reciprocal rank fusion.

    Each chunk accrues 1/(k + rank) from every list it appears in (rank is 1-based).
    Results are sorted by fused score descending, ties broken by chunk_uuid for
    determinism, and truncated to top_n when given.
    """
    scores: dict[UUID, float] = {}
    chunks: dict[UUID, SimpleChunk] = {}
    ranks: dict[UUID, dict[str, int]] = {}

    for label, hits in ranked_lists.items():
        for position, hit in enumerate(hits):
            rank = position + 1
            chunk_uuid = hit.chunk.chunk_uuid
            scores[chunk_uuid] = scores.get(chunk_uuid, 0.0) + 1.0 / (k + rank)
            chunks.setdefault(chunk_uuid, hit.chunk)
            label_ranks = ranks.setdefault(chunk_uuid, {})
            # A uuid should not appear twice in one ES list; keep the best rank if it does.
            if label not in label_ranks or rank < label_ranks[label]:
                label_ranks[label] = rank

    fused = [
        FusedChunk(
            chunk=chunks[chunk_uuid],
            rrf_score=scores[chunk_uuid],
            contributing_ranks=ranks[chunk_uuid],
        )
        for chunk_uuid in scores
    ]
    fused.sort(key=lambda f: (-f.rrf_score, str(f.chunk.chunk_uuid)))
    if top_n is not None:
        fused = fused[:top_n]
    return fused
