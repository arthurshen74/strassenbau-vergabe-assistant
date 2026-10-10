from __future__ import annotations

from uuid import uuid4

from shared.clients.search import lv_items_filter, plus_filter, simple_filter
from shared.clients.search.client import FIELD_PROJECT_UUID, FIELD_SOURCE_DOC_TYPE
from shared.models.enums import RetrievalModality, SourceDocType
from shared.services.retrieval.config import RetrievalConfig
from shared.services.retrieval.service import _resolve_scope


def test_lv_items_filter_scopes_project_and_lv_item_only() -> None:
    project_uuid = uuid4()
    terms = lv_items_filter(project_uuid)["bool"]["filter"]
    assert {"term": {FIELD_PROJECT_UUID: str(project_uuid)}} in terms
    assert {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.LV_ITEM.value}} in terms
    assert {"term": {FIELD_SOURCE_DOC_TYPE: SourceDocType.DOCUMENT.value}} not in terms


def test_simple_filter_spans_documents_and_forms() -> None:
    project_uuid = uuid4()
    assert simple_filter(project_uuid) == {
        "bool": {
            "filter": [
                {"term": {FIELD_PROJECT_UUID: str(project_uuid)}},
                {
                    "terms": {
                        FIELD_SOURCE_DOC_TYPE: [
                            SourceDocType.DOCUMENT.value,
                            SourceDocType.FORM.value,
                        ]
                    }
                },
            ]
        }
    }


def test_plus_filter_spans_documents_forms_and_every_lv_source() -> None:
    project_uuid = uuid4()
    assert plus_filter(project_uuid) == {
        "bool": {
            "filter": [
                {"term": {FIELD_PROJECT_UUID: str(project_uuid)}},
                {
                    "terms": {
                        FIELD_SOURCE_DOC_TYPE: [
                            SourceDocType.DOCUMENT.value,
                            SourceDocType.FORM.value,
                            SourceDocType.LV_ITEM.value,
                            SourceDocType.LV_TEXT.value,
                        ]
                    }
                },
            ]
        }
    }


def test_resolve_scope_needs_no_lv_document() -> None:
    project_uuid = uuid4()
    plus = RetrievalConfig(modality=RetrievalModality.PLUS)
    simple = RetrievalConfig(modality=RetrievalModality.SIMPLE)
    assert _resolve_scope(project_uuid, plus) == plus_filter(project_uuid)
    assert _resolve_scope(project_uuid, simple) == simple_filter(project_uuid)
