"""The pure helpers of the RAG ground-truth service: ref validation against a project's
documents, and the refs_missing flag on read."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.models.document import Document
from shared.models.enums import DocumentType, RagQuestionCategory, RagQuestionType
from shared.models.rag_ground_truth import RagGroundTruth, RagRef
from shared.services.rag_ground_truth import to_read, validate_refs


def _document(pages: int = 10) -> Document:
    now = datetime.now(timezone.utc)
    return Document(
        document_uuid=uuid4(),
        project_uuid=uuid4(),
        document_type=DocumentType.PROSE_DOCUMENT,
        file_name="baubeschreibung.pdf",
        number_of_pages=pages,
        created_at=now,
        updated_at=now,
    )


def _row(refs: list[RagRef]) -> RagGroundTruth:
    now = datetime.now(timezone.utc)
    return RagGroundTruth(
        rag_ground_truth_uuid=uuid4(),
        project_uuid=uuid4(),
        question="Wie viele Streckenabschnitte umfasst die Maßnahme?",
        gold_answer="4",
        refs=refs,
        question_type=RagQuestionType.AGGREGATION,
        category=RagQuestionCategory.KALKULATOR,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def test_validate_refs_accepts_known_document_and_page() -> None:
    doc = _document(pages=10)
    refs = [RagRef(document_uuid=doc.document_uuid, page=10)]
    assert validate_refs(refs, {doc.document_uuid: doc}) == []


def test_validate_refs_rejects_foreign_document() -> None:
    doc = _document()
    stranger = uuid4()
    problems = validate_refs(
        [RagRef(document_uuid=stranger, page=1)], {doc.document_uuid: doc}
    )
    assert len(problems) == 1
    assert str(stranger) in problems[0]


def test_validate_refs_rejects_page_beyond_document() -> None:
    doc = _document(pages=3)
    problems = validate_refs(
        [RagRef(document_uuid=doc.document_uuid, page=4)], {doc.document_uuid: doc}
    )
    assert len(problems) == 1
    assert "baubeschreibung.pdf" in problems[0]


def test_to_read_flags_missing_refs() -> None:
    doc_uuid: UUID = uuid4()
    assert to_read(_row([])).refs_missing is True
    assert to_read(_row([RagRef(document_uuid=doc_uuid, page=1)])).refs_missing is False
