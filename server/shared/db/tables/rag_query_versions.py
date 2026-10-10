from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from shared.db.metadata import metadata
from shared.models.enums import ProjectInfoQuery

_QUERY_KEYS_SQL = ", ".join(f"'{k.value}'" for k in ProjectInfoQuery)

rag_query_versions = Table(
    "rag_query_versions",
    metadata,
    Column(
        "rag_query_version_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("query_key", Text, nullable=False),
    # ISO 639-1, lower case.
    Column("language", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
    # Retrieval question: the embedding and BM25 input.
    Column("query_text", Text, nullable=False),
    # Output rule for the synthesis LLM; never part of the retrieval input.
    Column("answer_instruction", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(f"query_key IN ({_QUERY_KEYS_SQL})", name="query_key_valid"),
    CheckConstraint("language ~ '^[a-z]{2}$'", name="language_valid"),
    UniqueConstraint("query_key", "language", "version"),
)
