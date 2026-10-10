from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.models.document import NewDocument
from shared.models.enums import DocumentType, IngestStatus, PromptType, SourceDocType
from shared.models.lv_item import NewLVItem
from shared.models.project import NewProject, Project
from shared.models.prompt_version import NewPromptVersion, PromptVersion
from shared.models.simple_chunk import SimpleChunk
from shared.models.source_line import SourceLine


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_enum_values() -> None:
    assert DocumentType.LV_DOCUMENT == "LV_DOCUMENT"
    assert SourceDocType.LV_ITEM == "LV_ITEM"
    assert IngestStatus.QUEUED == "queued"
    assert {p.value for p in PromptType} == {
        "dispatcher",
        "project_chat",
        "aggregate_lv_membership",
        "multi_question_generator",
        "lv_extraction",
        "conversation_name",
        "ekt_calculator",
        "rezept_autor",
        "katalog_chat",
        "ekt_leistung_classify",
        "ekt_chat_values",
        "ekt_langtext_extract",
        "ekt_output_narrate",
        "project_context_resolve",
        "katalog_handbuch",
        "ner_fehleranalyse",
        "project_info_resolve",
    }


def test_project_round_trips() -> None:
    new = NewProject(
        vergabe_id="VG-1",
        project_name="A1",
        project_description="desc",
        vergabestelle="Behörde",
    )
    project = Project(
        project_uuid=uuid4(), created_at=_now(), updated_at=_now(), **new.model_dump()
    )
    assert Project.model_validate(project.model_dump()) == project


def test_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        NewProject(
            vergabe_id="x",
            project_name="y",
            project_description="z",
            vergabestelle="b",
            surprise="nope",
        )


def test_document_uses_enum_and_nullable_description() -> None:
    doc = NewDocument(
        project_uuid=uuid4(),
        document_type=DocumentType.LV_DOCUMENT,
        file_name="lv.pdf",
        number_of_pages=12,
    )
    assert doc.document_type is DocumentType.LV_DOCUMENT
    assert doc.document_description is None


def test_lv_item_menge_is_decimal_and_nullables_default() -> None:
    item = NewLVItem(
        document_uuid=uuid4(),
        oz="01.02.0030",
        kurztext="kurz",
        langtext="lang",
        menge=Decimal("2400.00"),
        einheit="m2",
    )
    assert isinstance(item.menge, Decimal)
    assert item.positionstyp is None
    assert item.level is None
    assert item.source_lines == []


def test_source_line_bbox_is_fixed_tuple() -> None:
    line = SourceLine(
        source_line_uuid=uuid4(),
        document_uuid=uuid4(),
        line_id=1,
        page=1,
        bbox=(0.0, 1.0, 2.0, 3.0),
        line_text="hello",
    )
    assert line.bbox == (0.0, 1.0, 2.0, 3.0)
    with pytest.raises(ValidationError):
        SourceLine(
            source_line_uuid=uuid4(),
            document_uuid=uuid4(),
            line_id=1,
            page=1,
            bbox=(0.0, 1.0, 2.0),
            line_text="hello",
        )


def test_prompt_version_round_trip() -> None:
    new = NewPromptVersion(
        prompt_type=PromptType.PROJECT_CHAT,
        model_name="anthropic/claude-sonnet-4.6",
        system_prompt="You answer.",
        temperature=0.2,
        top_p=0.9,
    )
    version = PromptVersion(
        prompt_version_uuid=uuid4(), version=1, created_at=_now(), **new.model_dump()
    )
    assert version.prompt_type is PromptType.PROJECT_CHAT
    assert version.temperature == 0.2
    assert version.top_p == 0.9


def test_simple_chunk_defaults() -> None:
    chunk = SimpleChunk(
        chunk_uuid=uuid4(),
        source_doc_uuid=uuid4(),
        source_doc_type=SourceDocType.LV_ITEM,
        source_doc_field="langtext_resolved",
        source_doc_pages=[1, 2],
        chunk_index=0,
        project_uuid=uuid4(),
        chunk_text="text",
        embedding=[0.1, 0.2],
        embedding_model="openai/text-embedding-3-small",
    )
    assert chunk.source_doc_language == "de"
    assert chunk.oz is None
