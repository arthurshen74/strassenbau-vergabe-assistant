from __future__ import annotations

import pytest
from shared.models.enums import DocumentType, FormRole, IngestStatus
from shared.services.ingestion.classify import (
    LV_DOCUMENT,
    PROSE_DOCUMENT,
    DocumentClassification,
)
from shared.services.ingestion.enqueue_policy import initial_ingest_status


def _form(role: FormRole, form_id: str | None) -> DocumentClassification:
    return DocumentClassification(
        document_type=DocumentType.FORM_DOCUMENT, form_role=role, form_id=form_id
    )


@pytest.mark.parametrize(
    "classification",
    [
        LV_DOCUMENT,
        PROSE_DOCUMENT,
        _form(FormRole.VERGABESTELLE, "FB 312-B"),
        _form(FormRole.UNBEKANNT, None),
        _form(FormRole.BIETER, None),
    ],
    ids=["lv", "prose", "vergabestelle-form", "unknown-form", "keyword-only-bieter"],
)
def test_everything_but_identified_bieter_forms_is_queued(
    classification: DocumentClassification,
) -> None:
    assert initial_ingest_status(classification) is IngestStatus.QUEUED


@pytest.mark.parametrize("form_id", ["FB 331-B", "HVA B-StB 121"])
def test_identified_bieter_form_is_skipped(form_id: str) -> None:
    assert (
        initial_ingest_status(_form(FormRole.BIETER, form_id)) is IngestStatus.SKIPPED
    )
