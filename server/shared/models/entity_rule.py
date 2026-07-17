"""Domain models for DB-backed EntityRuler rules.

`EntityRule` is one persisted row. `NewEntityRule` is the insert shape; the DB
fills the uuid and timestamps. `EntityRuleUpdate` is a partial patch where every
field is optional — an unset field leaves that column untouched (the repository
drops `None`s before building the UPDATE).

`pattern` is spaCy's token-pattern DSL: a bare phrase string or a list of
token-attribute dicts. It is genuinely heterogeneous (design D1), so it is typed
as the union rather than a modeled schema; spaCy validates it at the write
boundary before it is persisted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

EntityPattern = str | list[dict[str, Any]]


class EntityRule(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    entity_rule_uuid: UUID
    label: str
    pattern: EntityPattern
    pattern_id: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class NewEntityRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    pattern: EntityPattern
    pattern_id: str | None = None
    enabled: bool = True


class EntityRuleUpdate(BaseModel):
    """Partial patch; only the fields set on the instance are written."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    pattern: EntityPattern | None = None
    pattern_id: str | None = None
    enabled: bool | None = None
