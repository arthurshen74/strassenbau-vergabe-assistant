"""LV-level texts: the parse result's LVText rows and their LV_TEXT chunks."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from shared.models.enums import LVTextKind, LVTextPlacement, SourceDocType
from shared.models.lv_text import LVText
from shared.services.ingestion.chunking import SOURCE_DOC_FIELD_LV_TEXT, chunk_lv_text
from shared.services.ingestion.lv.types import AddTextBlock, LVParseResult, Remark


def test_to_new_lv_texts_orders_vortext_remarks_nachtext() -> None:
    document_uuid = uuid4()
    result = LVParseResult(
        items=[],
        warnings=[],
        add_texts=[
            AddTextBlock(LVTextPlacement.BEFORE_BOQ, "Vorbemerkungen", "VOB/B.", 0),
            AddTextBlock(LVTextPlacement.BEFORE_BOQ, None, "Baubeschreibung.", 1),
            AddTextBlock(LVTextPlacement.AFTER_BOQ, "Bietererklärung", "60 Tage.", 0),
        ],
        remarks=[
            Remark(
                oz=None, heading=None, body="Gilt für das LV.", parent_oz=None, index=0
            ),
            Remark(
                oz="01.0000", heading="H", body="Gilt für 01.", parent_oz="01", index=0
            ),
        ],
    )

    rows = result.to_new_lv_texts(document_uuid)

    assert [(r.sequence, r.kind, r.placement, r.index) for r in rows] == [
        (0, LVTextKind.ADD_TEXT, LVTextPlacement.BEFORE_BOQ, 0),
        (1, LVTextKind.ADD_TEXT, LVTextPlacement.BEFORE_BOQ, 1),
        (2, LVTextKind.REMARK, None, 0),
        (3, LVTextKind.REMARK, None, 0),
        (4, LVTextKind.ADD_TEXT, LVTextPlacement.AFTER_BOQ, 0),
    ]
    assert all(r.document_uuid == document_uuid for r in rows)
    assert (rows[0].heading, rows[0].body) == ("Vorbemerkungen", "VOB/B.")
    assert (rows[3].parent_oz, rows[3].oz, rows[3].heading) == ("01", "01.0000", "H")


def test_chunk_lv_text_joins_heading_and_body_and_carries_parent_oz() -> None:
    text = LVText(
        lv_text_uuid=uuid4(),
        document_uuid=uuid4(),
        kind=LVTextKind.REMARK,
        parent_oz="01.02",
        index=0,
        sequence=3,
        heading="Hinweis zu Bewuchs",
        body="Abrechnung nach Grundflächen.",
        last_ingestion=datetime.now(tz=UTC),
    )
    project_uuid = uuid4()

    drafts = chunk_lv_text(text, project_uuid=project_uuid)

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.source_doc_uuid == text.lv_text_uuid
    assert draft.source_doc_type is SourceDocType.LV_TEXT
    assert draft.source_doc_field == SOURCE_DOC_FIELD_LV_TEXT
    assert draft.oz == "01.02"
    assert draft.project_uuid == project_uuid
    assert draft.chunk_text == "Hinweis zu Bewuchs\nAbrechnung nach Grundflächen."
    assert draft.source_doc_pages == []
