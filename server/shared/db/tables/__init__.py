"""Importing this package registers every table on the shared metadata.

`metadata.create_all` only sees tables whose modules have been imported, so any
process that builds the schema (tests, bootstrap) must import this package first.
"""

from __future__ import annotations

from shared.db.tables.calculation_ground_truth import calculation_ground_truth
from shared.db.tables.conversations import conversations
from shared.db.tables.documents import documents
from shared.db.tables.embedding_cache import embedding_cache
from shared.db.tables.ingest_job_events import ingest_job_events
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.db.tables.ingestion_activity_log import ingestion_activity_log
from shared.db.tables.ingestion_activity_log_archive import ingestion_activity_log_archive
from shared.db.tables.lv_items import lv_items
from shared.db.tables.messages import messages
from shared.db.tables.openrouter_usage import openrouter_usage
from shared.db.tables.projects import projects
from shared.db.tables.prompt_execution_log import prompt_execution_log
from shared.db.tables.prompt_versions import prompt_versions
from shared.db.tables.source_lines import source_lines
from shared.db.tables.thumbnails import thumbnails
from shared.db.tables.variable_corrections import variable_corrections

__all__ = [
    "calculation_ground_truth",
    "conversations",
    "documents",
    "embedding_cache",
    "ingest_job_events",
    "ingest_jobs",
    "ingestion_activity_log",
    "ingestion_activity_log_archive",
    "lv_items",
    "messages",
    "openrouter_usage",
    "projects",
    "prompt_execution_log",
    "prompt_versions",
    "source_lines",
    "thumbnails",
    "variable_corrections",
]
