"""Unit tests for the document-footprint Elasticsearch query.

The tricky part this guards: an LV document's parsed items and texts are indexed as
LV_ITEM / LV_TEXT chunks keyed by their own row uuids, not by the document_uuid, so
deleting a document by document_uuid alone would leave those chunks behind.
"""

from __future__ import annotations

from uuid import uuid4

from shared.clients.search.client import (
    FIELD_PROJECT_UUID,
    FIELD_SOURCE_DOC_TYPE,
    FIELD_SOURCE_DOC_UUID,
    _document_footprint_query,
)
from shared.models.enums import SourceDocType


def test_footprint_query_without_lv_items_matches_only_document_chunks() -> None:
    project_uuid = uuid4()
    document_uuid = uuid4()

    query = _document_footprint_query(project_uuid, document_uuid, [])

    assert query["bool"]["filter"] == [
        {"term": {FIELD_PROJECT_UUID: str(project_uuid)}}
    ]
    should = query["bool"]["must"][0]["bool"]["should"]
    assert len(should) == 1
    assert should[0]["bool"]["filter"] == [
        {"term": {FIELD_SOURCE_DOC_UUID: str(document_uuid)}},
        {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.DOCUMENT.value}},
    ]


def test_footprint_query_with_lv_sources_adds_lv_clause() -> None:
    project_uuid = uuid4()
    document_uuid = uuid4()
    lv_source_uuids = [uuid4(), uuid4()]

    query = _document_footprint_query(project_uuid, document_uuid, lv_source_uuids)

    must_bool = query["bool"]["must"][0]["bool"]
    assert must_bool["minimum_should_match"] == 1
    should = must_bool["should"]
    assert len(should) == 2
    assert should[1]["bool"]["filter"] == [
        {"terms": {FIELD_SOURCE_DOC_UUID: [str(u) for u in lv_source_uuids]}},
        {
            "terms": {
                FIELD_SOURCE_DOC_TYPE: [
                    SourceDocType.LV_ITEM.value,
                    SourceDocType.LV_TEXT.value,
                ]
            }
        },
    ]
