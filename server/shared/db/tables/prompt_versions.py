from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from shared.db.metadata import metadata

prompt_versions = Table(
    "prompt_versions",
    metadata,
    Column(
        "prompt_version_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "prompt_uuid",
        Uuid(as_uuid=True),
        ForeignKey("prompts.prompt_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("version", Integer, nullable=False),
    Column("system_prompt", Text, nullable=False),
    Column("model_provider", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("model_endpoint", Text, nullable=True),
    Column("api_key_ref", Text, nullable=False),
    Column("temperature", Double, nullable=False),
    Column("top_p", Double, nullable=True),
    Column("max_tokens", Integer, nullable=False),
    Column("stop_sequences", ARRAY(Text), nullable=True),
    Column("output_schema_ref", Text, nullable=True),
    Column("tool_selection", JSONB, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint(
        "prompt_uuid", "version", name="uq_prompt_versions_prompt_uuid_version"
    ),
    CheckConstraint("version >= 1", name="version_positive"),
)
