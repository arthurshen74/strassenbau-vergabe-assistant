from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from shared.models.enums import SourceDocType
from shared.models.lv_item import LVItem
from shared.models.source_line import SourceLine
from shared.services.ingestion.chunking import (
    SOURCE_DOC_FIELD_DOCUMENT,
    SOURCE_DOC_FIELD_LV_ITEM,
    chunk_document,
    chunk_lv_item,
)


def _line(line_id: int, page: int, text: str) -> SourceLine:
    return SourceLine(
        source_line_uuid=uuid4(),
        document_uuid=uuid4(),
        line_id=line_id,
        page=page,
        bbox=(0, 0, 1, 1),
        line_text=text,
    )


def _lv_item(*, langtext: str, langtext_resolved: str | None) -> LVItem:
    return LVItem(
        lv_item_uuid=uuid4(),
        document_uuid=uuid4(),
        oz="1.1",
        kurztext="k",
        langtext=langtext,
        langtext_resolved=langtext_resolved,
        menge=Decimal("1"),
        einheit="m",
        stl_nr="21 109",
        source_lines=[],
        last_ingestion=datetime.now(UTC),
    )


def test_chunk_document_indexes_and_derives_pages() -> None:
    project, document = uuid4(), uuid4()
    lines = [_line(i, 1 if i < 3 else 2, f"line {i} " + "x" * 40) for i in range(6)]

    drafts = chunk_document(lines, project_uuid=project, document_uuid=document)

    assert drafts
    assert [d.chunk_index for d in drafts] == list(range(len(drafts)))
    for draft in drafts:
        assert draft.source_doc_type == SourceDocType.DOCUMENT
        assert draft.source_doc_field == SOURCE_DOC_FIELD_DOCUMENT
        assert draft.source_doc_uuid == document
        assert draft.project_uuid == project
        assert draft.oz is None and draft.stl_nr is None
    # The single small chunk spans both pages.
    assert drafts[0].source_doc_pages == [1, 2]


def test_chunk_lv_item_prefers_resolved_and_denormalizes_oz() -> None:
    item = _lv_item(langtext="VERBATIM", langtext_resolved="RESOLVED BODY " + "y" * 40)

    drafts = chunk_lv_item(item, pages=[2, 3], project_uuid=uuid4())

    assert drafts
    assert "RESOLVED" in drafts[0].chunk_text and "VERBATIM" not in drafts[0].chunk_text
    for draft in drafts:
        assert draft.source_doc_type == SourceDocType.LV_ITEM
        assert draft.source_doc_field == SOURCE_DOC_FIELD_LV_ITEM
        assert draft.source_doc_uuid == item.lv_item_uuid
        assert draft.oz == "1.1" and draft.stl_nr == "21 109"
        assert draft.source_doc_pages == [2, 3]


def test_chunk_lv_item_falls_back_to_langtext_when_unresolved() -> None:
    item = _lv_item(langtext="ONLY VERBATIM TEXT", langtext_resolved=None)

    drafts = chunk_lv_item(item, pages=[1], project_uuid=uuid4())

    assert "ONLY VERBATIM TEXT" in drafts[0].chunk_text
