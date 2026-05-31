from __future__ import annotations

from sqlalchemy import Column, DateTime, Table, Text, func, text
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata

projects = Table(
    "projects",
    metadata,
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("vergabe_id", Text, nullable=False),
    Column("project_name", Text, nullable=False),
    Column("project_description", Text, nullable=False),
    Column("vergabestelle", Text, nullable=False),
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
)
