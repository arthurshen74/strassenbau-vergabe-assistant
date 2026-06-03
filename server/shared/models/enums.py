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


class RetrievalModality(StrEnum):
    SIMPLE = "SIMPLE"
    PLUS = "PLUS"


class IngestStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class PromptType(StrEnum):
    DISPATCHER = "dispatcher"
    PROJECT_CHAT = "project_chat"
    AGGREGATE_LV_MEMBERSHIP = "aggregate_lv_membership"
    MULTI_QUESTION_GENERATOR = "multi_question_generator"
    LV_EXTRACTION = "lv_extraction"
    CONVERSATION_NAME = "conversation_name"


class UsageOperation(StrEnum):
    CHAT = "CHAT"
    EMBEDDING = "EMBEDDING"
    RERANK = "RERANK"


class MessageKind(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"
