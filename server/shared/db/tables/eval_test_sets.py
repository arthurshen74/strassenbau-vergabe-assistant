from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from shared.db.metadata import metadata

eval_test_sets = Table(
    "eval_test_sets",
    metadata,
    Column(
        "test_set_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("config", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
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
    UniqueConstraint("name", name="uq_eval_test_sets_name"),
)
