"""Unit coverage for the pure project-chat pieces: the turn-config mapping, the
classifier's clean-history filter, and how a context source resolves its page thumbnail."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from shared.models.enums import (
    MessageKind,
    RetrievalModality,
    SourceDocType,
)
from shared.models.message import Message
from shared.models.retrieval_request_schema import TurnRetrievalConfig
from shared.models.simple_chunk import SimpleChunk
from shared.services.messages import to_user_assistant_messages
from shared.services.project_chat import config_from_request
from shared.services.retrieval.service import _thumbnail_ref


def _msg(kind: MessageKind, content: str | None) -> Message:
    return Message(
        message_uuid=uuid4(),
        conversation_uuid=uuid4(),
        kind=kind,
        content=content,
        created_at=datetime.now(UTC),
    )


def _chunk(source_doc_type: SourceDocType, pages: list[int]) -> SimpleChunk:
    return SimpleChunk(
        chunk_uuid=uuid4(),
        source_doc_uuid=uuid4(),
        source_doc_type=source_doc_type,
        source_doc_field="chunk_text",
        source_doc_pages=pages,
        chunk_index=0,
        project_uuid=uuid4(),
        chunk_text="x",
        embedding=[],
        embedding_model="m",
    )


def test_config_from_request_defaults_when_absent() -> None:
    config = config_from_request(None)
    assert config.modality is RetrievalModality.SIMPLE
    assert not config.multi_query and not config.use_bm25 and not config.use_cross_encoder


def test_config_from_request_maps_fields() -> None:
    dto = TurnRetrievalConfig(
        modality=RetrievalModality.PLUS,
        multi_query=True,
        use_bm25=True,
        use_cross_encoder=True,
    )
    config = config_from_request(dto)
    assert config.modality is RetrievalModality.PLUS
    assert config.multi_query and config.use_bm25 and config.use_cross_encoder


def test_to_user_assistant_messages_drops_tool_rows_and_empty_assistants() -> None:
    stored = [
        _msg(MessageKind.USER, "was ist OZ 1.2?"),
        _msg(MessageKind.FUNCTION_CALL, None),
        _msg(MessageKind.FUNCTION_CALL_OUTPUT, None),
        _msg(MessageKind.ASSISTANT, "Position 1.2: Tragschicht"),
        _msg(MessageKind.ASSISTANT, None),
    ]
    out = to_user_assistant_messages(stored)
    assert [m.role for m in out] == ["user", "assistant"]
    assert out[0].content == "was ist OZ 1.2?"
    assert out[1].content == "Position 1.2: Tragschicht"


def test_thumbnail_ref_document_uses_own_doc() -> None:
    chunk = _chunk(SourceDocType.DOCUMENT, [3, 4])
    ref = _thumbnail_ref(chunk)
    assert ref is not None
    assert ref.document_uuid == chunk.source_doc_uuid
    assert ref.page_number == 3


def test_thumbnail_ref_absent_for_lv_chunks_and_pageless_documents() -> None:
    assert _thumbnail_ref(_chunk(SourceDocType.DOCUMENT, [])) is None
    assert _thumbnail_ref(_chunk(SourceDocType.LV_ITEM, [2])) is None
    assert _thumbnail_ref(_chunk(SourceDocType.LV_TEXT, [])) is None
