from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata
from shared.models.enums import MessageKind

# One table for every turn shape, discriminated by `kind`:
#   user / assistant       -> content
#   function_call          -> call_id, tool_name, arguments
#   function_call_output   -> call_id, tool_name, success, data, errors
_MESSAGE_KINDS_SQL = ", ".join(f"'{k.value}'" for k in MessageKind)

messages = Table(
    "messages",
    metadata,
    Column(
        "message_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column(
        "conversation_uuid",
        UUID(as_uuid=True),
        ForeignKey("conversations.conversation_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("kind", Text, nullable=False),
    Column("content", Text, nullable=True),
    Column("call_id", Text, nullable=True),
    Column("tool_name", Text, nullable=True),
    Column("arguments", JSONB, nullable=True),
    Column("success", Boolean, nullable=True),
    Column("data", JSONB, nullable=True),
    Column("errors", JSONB, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(f"kind IN ({_MESSAGE_KINDS_SQL})", name="message_kind_valid"),
)
