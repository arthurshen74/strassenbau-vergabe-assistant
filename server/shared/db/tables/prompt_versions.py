from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata
from shared.models.enums import PromptType

_PROMPT_TYPES_SQL = ", ".join(f"'{p.value}'" for p in PromptType)

prompt_versions = Table(
    "prompt_versions",
    metadata,
    Column(
        "prompt_version_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("prompt_type", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("system_prompt", Text, nullable=False),
    Column("temperature", Float, nullable=True),
    Column("top_p", Float, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(f"prompt_type IN ({_PROMPT_TYPES_SQL})", name="prompt_type_valid"),
    UniqueConstraint("prompt_type", "version"),
)
