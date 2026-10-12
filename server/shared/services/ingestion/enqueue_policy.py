"""Decides whether a freshly classified document is ingested now or parked.

Classification (`ingestion.classify`) says what a document is; this module says what the
ingest queue should do with it. The two are kept apart so that each rule can be read and
tested on its own: a change to "what counts as a form" never touches "which forms we
ingest", and vice versa.

Today there is one rule. A Bieter form is a template the bidder fills in, so at upload
time it is empty and there is nothing to extract; it is recorded as a document but its
job starts SKIPPED, which the worker never claims. A requeue from the ingest console
ingests it on purpose. The rule only fires when the Bieter role comes from an identified
Formblatt (`form_id` set): a role from a title keyword alone is a hint, and a wrongly
skipped Vergabestelle explanation sheet is a lost document, while an ingested blank
Bieter form merely yields its static prose. Every other document starts QUEUED.
"""

from __future__ import annotations

from shared.models.enums import FormRole, IngestStatus
from shared.services.ingestion.classify import DocumentClassification


def initial_ingest_status(classification: DocumentClassification) -> IngestStatus:
    """The status a document's ingest job is created with."""
    if is_bieter_form(classification):
        return IngestStatus.SKIPPED
    return IngestStatus.QUEUED


def is_bieter_form(classification: DocumentClassification) -> bool:
    """An identified Formblatt the bidder fills in, empty at upload."""
    return (
        classification.form_role is FormRole.BIETER
        and classification.form_id is not None
    )
