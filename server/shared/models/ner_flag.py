"""Domain models for NER error flags: the captured misprediction, its snapshotted
context, and the LLM error analysis persisted onto it.

A flag is a point-in-time record. `entity_snapshot` freezes the flag-time entity list
and `suggested_rule` holds the advisory LLM fix; the effective category (user override
winning over the LLM assignment) is what the dashboard aggregates.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field

from shared.models.entity_rule import EntityPattern
from shared.models.enums import NerFailureCategory, NerFlagKind, NerFlagStatus


class SnapshotEntity(BaseModel):
    """One entity from the flag-time extraction, frozen onto the flag."""

    model_config = ConfigDict(extra="forbid")

    text: str
    label: str
    pattern_id: str | None = None


class SuggestedRule(BaseModel):
    """Advisory EntityRuler fix proposed by the LLM (never auto-applied). `pattern` is
    nullable: a partial suggestion must not discard the whole analysis."""

    model_config = ConfigDict(extra="forbid")

    label: str
    pattern: EntityPattern | None = None
    pattern_id: str | None = None


class NewNerFlag(BaseModel):
    """Create shape: the observed misprediction and its snapshotted context."""

    model_config = ConfigDict(extra="forbid")

    kind: NerFlagKind
    span_text: str
    span_start: int
    span_end: int
    sentence_text: str
    label: str
    expected_label: str | None = None
    user_comment: str
    source_text: str
    entity_snapshot: list[SnapshotEntity]
    lv_item_uuid: UUID | None = None
    document_uuid: UUID | None = None


class NerFlag(NewNerFlag):
    """Persisted flag with DB-assigned fields and the LLM analysis result."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    ner_flag_uuid: UUID
    category: NerFailureCategory | None = None
    category_override: NerFailureCategory | None = None
    llm_analysis: str | None = None
    suggested_rule: SuggestedRule | None = None
    llm_model: str | None = None
    prompt_version: int | None = None
    spacy_model_version: str | None = None
    analyzed_at: datetime | None = None
    status: NerFlagStatus
    resolved_note: str | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def effective_category(self) -> NerFailureCategory | None:
        """User override wins over the LLM assignment."""
        return self.category_override or self.category


class NerFlagUpdate(BaseModel):
    """Partial patch: category override and resolve/reopen with a note."""

    model_config = ConfigDict(extra="forbid")

    category_override: NerFailureCategory | None = None
    status: NerFlagStatus | None = None
    resolved_note: str | None = None


class NerCategoryCount(BaseModel):
    """Per-effective-category flag tally, split by status. `category` None =
    un-analyzed."""

    model_config = ConfigDict(extra="forbid")

    category: NerFailureCategory | None = None
    open_count: int
    resolved_count: int
    total: int


class NerFlagSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    by_category: list[NerCategoryCount]
