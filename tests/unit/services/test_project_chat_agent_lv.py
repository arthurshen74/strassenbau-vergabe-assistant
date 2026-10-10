"""LV tool output of the project-chat agent across several LV documents."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from shared.models.document import Document
from shared.models.enums import DocumentType
from shared.models.lv_item import LVItem
from shared.services.project_chat_agent import (
    RESULT_FILE_NAME,
    _dump_item,
    _format_groups,
)


def _lv_document(file_name: str) -> Document:
    now = datetime.now(tz=UTC)
    return Document(
        document_uuid=uuid4(),
        project_uuid=uuid4(),
        document_type=DocumentType.LV_DOCUMENT,
        file_name=file_name,
        number_of_pages=0,
        created_at=now,
        updated_at=now,
    )


def _item(document_uuid: UUID, oz: str) -> LVItem:
    return LVItem(
        lv_item_uuid=uuid4(),
        document_uuid=document_uuid,
        oz=oz,
        kurztext=f"kurz {oz}",
        langtext=f"lang {oz}",
        menge=Decimal("2"),
        einheit="m",
        last_ingestion=datetime.now(tz=UTC),
    )


def test_format_groups_heads_each_lv_file() -> None:
    los1, los2 = _lv_document("Los1.x83"), _lv_document("Los2.d83")
    text = _format_groups(
        [
            (los1, [_item(los1.document_uuid, "01.0010")]),
            (los2, [_item(los2.document_uuid, "01.0010")]),
        ]
    )
    assert text == (
        "LV-Datei Los1.x83:\n01.0010 | kurz 01.0010 | 2 m\n\n"
        "LV-Datei Los2.d83:\n01.0010 | kurz 01.0010 | 2 m"
    )


def test_format_groups_without_items() -> None:
    assert _format_groups([]) == "Keine Positionen gefunden."
    assert _format_groups([(_lv_document("a.x83"), [])]) == "Keine Positionen gefunden."


def test_dump_item_carries_document_and_file_name() -> None:
    doc = _lv_document("Los1.x83")
    dumped = _dump_item(_item(doc.document_uuid, "01.0010"), doc.file_name)
    assert dumped["document_uuid"] == str(doc.document_uuid)
    assert dumped[RESULT_FILE_NAME] == "Los1.x83"
