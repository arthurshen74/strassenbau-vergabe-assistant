from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Table, Text, Uuid, func, text

from shared.db.metadata import metadata

projects = Table(
    "projects",
    metadata,
    Column(
        "project_id",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("project_name", Text, nullable=False),
    Column("project_description", Text, nullable=True),
    Column("vergabe_stelle", Text, nullable=False),
    Column("project_start", Date, nullable=True),
    Column("project_location", Text, nullable=False),
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
