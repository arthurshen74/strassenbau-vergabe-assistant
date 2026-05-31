"""Controlled value sets shared across domain models, Core table CHECKs, and the ES index.

These enums are the single source of truth for every discriminator in the data model; both the
write side (table constraints, indexing) and the read side (queries, filters) import the same
member rather than re-typing the literal.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentType(StrEnum):
    LV_DOCUMENT = "LV_DOCUMENT"
    PROSE_DOCUMENT = "PROSE_DOCUMENT"


class SourceDocType(StrEnum):
    LV_ITEM = "LV_ITEM"
    DOCUMENT = "DOCUMENT"


class IngestStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class PromptType(StrEnum):
    DISPATCHER = "dispatcher"
    PROJECT_CHAT = "project_chat"
    CLASSIFY_PROJECT_CHAT_USER_MESSAGE = "classify_project_chat_user_message"
    MULTI_QUESTION_GENERATOR = "multi_question_generator"
    LV_EXTRACTION = "lv_extraction"
