from __future__ import annotations

from uuid import UUID

from shared.clients.search import ScoredChunk
from shared.models.enums import SourceDocType
from shared.models.simple_chunk import SimpleChunk
from shared.services.retrieval.rrf import RRF_K, reciprocal_rank_fusion

_PROJECT = UUID("22222222-2222-2222-2222-222222222222")
_DOC = UUID("11111111-1111-1111-1111-111111111111")


def _chunk(suffix: int) -> SimpleChunk:
    return SimpleChunk(
        chunk_uuid=UUID(f"00000000-0000-0000-0000-{suffix:012d}"),
        source_doc_uuid=_DOC,
        source_doc_type=SourceDocType.DOCUMENT,
        source_doc_field="body",
        chunk_index=suffix,
        project_uuid=_PROJECT,
        chunk_text=f"chunk {suffix}",
        embedding=[0.0],
        embedding_model="test-model",
    )


def _scored(chunk: SimpleChunk, score: float) -> ScoredChunk:
    return ScoredChunk(chunk=chunk, score=score)


def test_empty_input_returns_empty() -> None:
    assert reciprocal_rank_fusion({}) == []


def test_single_list_is_monotonic_passthrough() -> None:
    chunks = [_chunk(i) for i in range(3)]
    fused = reciprocal_rank_fusion({"q0:dense": [_scored(c, 1.0) for c in chunks]})

    assert [f.chunk.chunk_uuid for f in fused] == [c.chunk_uuid for c in chunks]
    scores = [f.rrf_score for f in fused]
    assert scores == sorted(scores, reverse=True)
    assert fused[0].rrf_score == 1.0 / (RRF_K + 1)
    assert fused[0].contributing_ranks == {"q0:dense": 1}


def test_chunk_in_two_lists_sums_reciprocal_ranks_and_dedups() -> None:
    shared_chunk = _chunk(0)
    only_a = _chunk(1)
    only_b = _chunk(2)
    ranked = {
        "q0:dense": [_scored(only_a, 1.0), _scored(shared_chunk, 0.9)],  # shared at rank 2
        "q0:lexical": [_scored(shared_chunk, 5.0), _scored(only_b, 4.0)],  # shared at rank 1
    }

    fused = reciprocal_rank_fusion(ranked)

    assert len(fused) == 3  # three distinct chunks despite shared appearing twice
    by_uuid = {f.chunk.chunk_uuid: f for f in fused}
    shared = by_uuid[shared_chunk.chunk_uuid]
    assert shared.rrf_score == 1.0 / (RRF_K + 2) + 1.0 / (RRF_K + 1)
    assert shared.contributing_ranks == {"q0:dense": 2, "q0:lexical": 1}
    # present in both lists, so it outranks the single-list chunks
    assert fused[0].chunk.chunk_uuid == shared_chunk.chunk_uuid


def test_top_n_truncates() -> None:
    chunks = [_chunk(i) for i in range(5)]
    fused = reciprocal_rank_fusion(
        {"q0:dense": [_scored(c, 1.0) for c in chunks]}, top_n=2
    )

    assert [f.chunk.chunk_uuid for f in fused] == [chunks[0].chunk_uuid, chunks[1].chunk_uuid]


def test_ties_break_by_chunk_uuid() -> None:
    high = _chunk(9)
    low = _chunk(1)
    ranked = {
        "q0:dense": [_scored(high, 1.0)],
        "q1:dense": [_scored(low, 1.0)],
    }

    fused = reciprocal_rank_fusion(ranked)

    assert fused[0].rrf_score == fused[1].rrf_score
    assert fused[0].chunk.chunk_uuid == low.chunk_uuid  # ascending uuid string
    assert fused[1].chunk.chunk_uuid == high.chunk_uuid
