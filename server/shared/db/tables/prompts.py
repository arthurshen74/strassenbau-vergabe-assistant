from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)

from shared.db.metadata import metadata

prompts = Table(
    "prompts",
    metadata,
    Column(
        "prompt_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("slug", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column(
        "is_archived",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
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
        onupdate=func.now(),
    ),
    UniqueConstraint("slug", name="uq_prompts_slug"),
)
