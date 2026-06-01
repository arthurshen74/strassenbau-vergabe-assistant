from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata
from shared.models.enums import PromptType

# prompt_type records which dispatcher drives the conversation (e.g. dispatcher, project_chat).
_PROMPT_TYPES_SQL = ", ".join(f"'{p.value}'" for p in PromptType)

conversations = Table(
    "conversations",
    metadata,
    Column(
        "conversation_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    # Owner lives in the auth DB; stored here as a plain UUID (the domain DB never joins to auth).
    Column("user_uuid", UUID(as_uuid=True), nullable=False, index=True),
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=True,
        index=True,
    ),
    Column("prompt_type", Text, nullable=False),
    Column("title", Text, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        f"prompt_type IN ({_PROMPT_TYPES_SQL})", name="conversation_prompt_type_valid"
    ),
)
