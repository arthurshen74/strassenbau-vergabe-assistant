"""Importing this package registers every table on the shared metadata.

`metadata.create_all` only sees tables whose modules have been imported, so any
process that builds the schema (tests, bootstrap) must import this package first.
"""

from __future__ import annotations

from shared.db.tables.documents import documents
from shared.db.tables.ingest_job_events import ingest_job_events
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.db.tables.lv_items import lv_items
from shared.db.tables.openrouter_usage import openrouter_usage
from shared.db.tables.projects import projects
from shared.db.tables.prompt_versions import prompt_versions
from shared.db.tables.source_lines import source_lines
from shared.db.tables.thumbnails import thumbnails

__all__ = [
    "documents",
    "ingest_job_events",
    "ingest_jobs",
    "lv_items",
    "openrouter_usage",
    "projects",
    "prompt_versions",
    "source_lines",
    "thumbnails",
]
