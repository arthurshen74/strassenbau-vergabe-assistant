from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.db.metadata import metadata

# Rich observability log: one row per LLM call, capturing the full request and response.
# Independent of openrouter_usage (cost) -- correlate via request_id when present.
prompt_execution_log = Table(
    "prompt_execution_log",
    metadata,
    Column(
        "log_uuid",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("prompt_type", Text, nullable=True),
    Column("prompt_version", Integer, nullable=True),
    Column("model", Text, nullable=False),
    Column("provider_url", Text, nullable=True),
    # Request: the system prompt is also present inside `messages`; surfaced here for quick scans.
    Column("system_prompt", Text, nullable=True),
    Column("messages", JSONB, nullable=False),
    Column("tools", JSONB, nullable=True),
    Column("response_format", JSONB, nullable=True),
    # Response: text and tool_calls are mutually exclusive per turn; structured set only for
    # response_format calls.
    Column("response_text", Text, nullable=True),
    Column("response_tool_calls", JSONB, nullable=True),
    Column("response_structured", JSONB, nullable=True),
    Column("finish_reason", Text, nullable=True),
    Column("tokens_in", Integer, nullable=True),
    Column("tokens_out", Integer, nullable=True),
    Column("latency_ms", Integer, nullable=True),
    Column("request_id", Text, nullable=True),
    # Attribution: SET NULL so the log outlives a deleted project/job.
    Column(
        "project_uuid",
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column(
        "ingest_job_uuid",
        UUID(as_uuid=True),
        ForeignKey("ingest_jobs.job_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column(
        "conversation_uuid",
        UUID(as_uuid=True),
        ForeignKey("conversations.conversation_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column("success", Boolean, nullable=False),
    Column("error_message", Text, nullable=True),
    Column("sent_at", DateTime(timezone=True), nullable=True),
    Column("returned_at", DateTime(timezone=True), nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
