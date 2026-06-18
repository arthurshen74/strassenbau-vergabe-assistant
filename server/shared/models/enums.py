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
    # ekt_calculator is a conversation discriminator (a position chat that owns a calculator run),
    # not a seeded prompt; the position chat itself runs on PROJECT_CHAT. The four ekt_* below are
    # the EKT calculation graph's structured LLM prompts (shared/services/calculator/llm_calls.py).
    EKT_CALCULATOR = "ekt_calculator"
    EKT_CLASSIFY = "ekt_classify"
    EKT_RESOLVE_DRIVER = "ekt_resolve_driver"
    EKT_SELECT_METHOD = "ekt_select_method"
    EKT_SEED_DRIVERS = "ekt_seed_drivers"


class CalculationStatus(StrEnum):
    """Lifecycle of an ekt_calculator conversation's graph run."""

    # Created and shown as a chat gate; the graph has not started. The user can discuss the position
    # (project chat) or ask to run it, which advances to RUNNING.
    AWAITING_START = "awaiting_start"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETE = "complete"
    FAILED = "failed"


class UsageOperation(StrEnum):
    CHAT = "CHAT"
    EMBEDDING = "EMBEDDING"
    RERANK = "RERANK"


class MessageKind(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"
