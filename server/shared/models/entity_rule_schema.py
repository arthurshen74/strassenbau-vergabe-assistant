"""API schemas for the entity_rules resource: Create / Read / Update.

Mirrors models/entity_rule.py as boundary types for /entity-rules/* routes. The pattern
travels as raw JSON (spaCy's DSL, design D1); the route validates it against a scratch
spaCy pipeline before persisting (design D7).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.entity_rule import EntityPattern


class EntityRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    entity_rule_uuid: UUID
    label: str
    pattern: EntityPattern
    pattern_id: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class EntityRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    pattern: EntityPattern
    pattern_id: str | None = None
    enabled: bool = True


class EntityRuleUpdate(BaseModel):
    """Partial patch; only fields present in the request body are applied."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    pattern: EntityPattern | None = None
    pattern_id: str | None = None
    enabled: bool | None = None
