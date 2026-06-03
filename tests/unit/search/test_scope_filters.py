from __future__ import annotations

from uuid import uuid4

from shared.clients.search import lv_items_filter
from shared.clients.search.client import FIELD_PROJECT_UUID, FIELD_SOURCE_DOC_TYPE
from shared.models.enums import SourceDocType


def test_lv_items_filter_scopes_project_and_lv_item_only() -> None:
    project_uuid = uuid4()
    terms = lv_items_filter(project_uuid)["bool"]["filter"]
    assert {"term": {FIELD_PROJECT_UUID: str(project_uuid)}} in terms
    assert {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.LV_ITEM.value}} in terms
    assert {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.DOCUMENT.value}} not in terms
