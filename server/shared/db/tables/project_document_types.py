from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)

from shared.db.metadata import metadata

project_document_types = Table(
    "project_document_types",
    metadata,
    Column(
        "document_type_uuid",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("document_type", Text, nullable=False),
    Column("document_type_description", Text, nullable=True),
    Column("form_type_standard", Text, nullable=True),
    Column("form_type_number", Integer, nullable=True),
    UniqueConstraint(
        "document_type",
        name="uq_project_document_types_document_type",
    ),
    CheckConstraint(
        "form_type_standard IS NULL OR form_type_standard IN ('HVA StB', 'VHB')",
        name="form_type_standard",
    ),
)
