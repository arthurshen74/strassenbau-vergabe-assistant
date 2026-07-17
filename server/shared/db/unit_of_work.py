"""Unit of Work: one connection and transaction shared by every repository.

A write that spans aggregates (e.g. create a document, its ingest job, and the
first job event) goes through a single `UnitOfWork` so the repositories enlist in
the same transaction and commit or roll back together.

Commit and rollback are automatic, driven by how control leaves the
`async with unit_of_work(engine) as uow:` block: a clean exit commits, and any
exception escaping the block rolls back and then propagates. This is handled by
`engine.begin()`; callers never call commit or rollback themselves. An exception
caught and swallowed inside the block does not roll back.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from shared.repositories.conversations import ConversationRepository
from shared.repositories.document_layout_regions import DocumentLayoutRegionRepository
from shared.repositories.documents import DocumentRepository
from shared.repositories.eval_results import EvalResultRepository
from shared.repositories.eval_run_events import EvalRunEventRepository
from shared.repositories.eval_runs import EvalRunRepository
from shared.repositories.ground_truth import GroundTruthRepository
from shared.repositories.ingest_job_events import IngestJobEventRepository
from shared.repositories.ingest_jobs import IngestJobRepository
from shared.repositories.ingestion_activity import IngestionActivityLogRepository
from shared.repositories.katalog import KatalogRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.messages import MessageRepository
from shared.repositories.nlp_render_cache import NlpRenderCacheRepository
from shared.repositories.openrouter_usage import OpenRouterUsageRepository
from shared.repositories.project_context_values import ProjectContextValueRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.prompt_execution_log import PromptExecutionLogRepository
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.repositories.source_lines import SourceLineRepository
from shared.repositories.thumbnails import ThumbnailRepository
from shared.repositories.variable_corrections import VariableCorrectionRepository


class UnitOfWork:
    """Owns a connection and a transaction; exposes repositories that share them."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn
        self.projects = ProjectRepository(conn)
        self.documents = DocumentRepository(conn)
        self.source_lines = SourceLineRepository(conn)
        self.thumbnails = ThumbnailRepository(conn)
        self.ingest_jobs = IngestJobRepository(conn)
        self.ingest_job_events = IngestJobEventRepository(conn)
        self.ingestion_activity = IngestionActivityLogRepository(conn)
        self.lv_items = LVItemRepository(conn)
        self.prompt_versions = PromptVersionRepository(conn)
        self.conversations = ConversationRepository(conn)
        self.messages = MessageRepository(conn)
        self.ground_truth = GroundTruthRepository(conn)
        self.variable_corrections = VariableCorrectionRepository(conn)
        self.eval_runs = EvalRunRepository(conn)
        self.eval_run_events = EvalRunEventRepository(conn)
        self.eval_results = EvalResultRepository(conn)
        self.project_context_values = ProjectContextValueRepository(conn)
        self.katalog = KatalogRepository(conn)
        self.document_layout_regions = DocumentLayoutRegionRepository(conn)
        self.nlp_render_cache = NlpRenderCacheRepository(conn)
        # Registered for read/report composition; the Database*Sinks write independently.
        self.openrouter_usage = OpenRouterUsageRepository(conn)
        self.prompt_execution_log = PromptExecutionLogRepository(conn)


@asynccontextmanager
async def unit_of_work(engine: AsyncEngine) -> AsyncIterator[UnitOfWork]:
    """Open a transaction and yield a UnitOfWork; commit on success, roll back on error."""
    async with engine.begin() as conn:
        yield UnitOfWork(conn)
